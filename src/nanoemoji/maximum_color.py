# Copyright 2022 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Generates color tables to provide support for a wide range of browsers.

Requires input font have vector color capability, that is either an SVG table
or COLR/CPAL.

https://www.youtube.com/watch?v=HLddvNiXym4

Sample usage:

maximum_color MySvgFont.ttf"""
from absl import app
from absl import flags
from absl import logging
from fontTools import ttLib
from nanoemoji.colr_to_svg import colr_glyphs
from nanoemoji.extract_svgs import svg_glyphs
from nanoemoji.ninja import (
    build_dir,
    gen_ninja,
    maybe_run_ninja,
    module_rule,
    rel_build,
    NinjaWriter,
)
from nanoemoji.util import only
from pathlib import Path


_SVG2COLR_GLYPHMAP = "svg2colr.glyphmap"
_SVG2COLR_CONFIG = "svg2colr.toml"

_COLR2SVG_GLYPHMAP = "colr2svg.glyphmap"
_COLR2SVG_CONFIG = "colr2svg.toml"

FLAGS = flags.FLAGS


flags.DEFINE_bool(
    "destroy_non_color_glyphs",
    True,
    "If true feel free to obliterate any existing glyf/cff content, e.g. fallback glyphs",
)


def _vector_color_table(font: ttLib.TTFont) -> str:
    has_svg = "SVG " in font
    has_colr = "COLR" in font
    if has_svg == has_colr:
        raise ValueError("Must have one of COLR, SVG")

    if has_svg:
        return "SVG "
    if has_colr:
        return "COLR"

    raise AssertionError("Impossible")


def svg_extract_dir() -> Path:
    return build_dir() / "svg_dump"


def svg_generate_dir() -> Path:
    return build_dir() / "svg_generate"


def picosvg_dir() -> Path:
    return build_dir() / "picosvg"


def picosvg_dest(input_svg: Path) -> Path:
    return picosvg_dir() / input_svg.name


def _write_preamble(nw: NinjaWriter, input_font: Path):
    module_rule(
        nw,
        "extract_svgs_from_otsvg",
        f"--output_dir {rel_build(svg_extract_dir())} $in $out",
    )
    nw.newline()

    module_rule(
        nw,
        "generate_svgs_from_colr",
        f"--output_dir {rel_build(svg_generate_dir())} $in $out",
    )
    nw.newline()

    module_rule(
        nw,
        "write_glyphmap_for_glyph_svgs",
        f"--output_file $out @$out.rsp",
        rspfile="$out.rsp",
        rspfile_content="$in",
    )
    nw.newline()

    module_rule(
        nw,
        "write_config_for_mergeable",
        "--color_format glyf_colr_1 $in $out",
        rule_name="write_glyf_colr_1_config",
    )
    nw.newline()

    module_rule(
        nw,
        "write_config_for_mergeable",
        "--color_format picosvg $in $out",
        rule_name="write_picosvg_config",
    )
    nw.newline()

    module_rule(
        nw,
        "write_font",
        f"--glyphmap_file {_SVG2COLR_GLYPHMAP} --config_file {_SVG2COLR_CONFIG} --output_file $out",
        rule_name="write_colr_font_from_svg_dump",
    )
    nw.newline()

    module_rule(
        nw,
        "write_font",
        f"--glyphmap_file {_COLR2SVG_GLYPHMAP} --config_file {_COLR2SVG_CONFIG} --output_file $out",
        rule_name="write_svg_font_from_generated_svgs",
    )
    nw.newline()

    nw.rule(
        f"picosvg",
        f"picosvg --output_file $out $in",
    )
    nw.newline()

    module_rule(
        nw,
        "glue_together",
        f"--color_table COLR --target_font {input_font} --donor_font $in --output_file $out",
        rule_name="copy_colr_from_svg2colr",
    )
    nw.newline()

    module_rule(
        nw,
        "glue_together",
        f"--color_table SVG --target_font {input_font} --donor_font $in --output_file $out",
        rule_name="copy_svg_from_colr2svg",
    )
    nw.newline()


def _generate_svg_from_colr(nw: NinjaWriter, input_font: Path, font: ttLib.TTFont):
    # generate svgs
    svg_files = [
        rel_build(svg_generate_dir() / f"{gid:05d}.svg") for gid in colr_glyphs(font)
    ]
    nw.build(svg_files, "generate_svgs_from_colr", input_font)
    nw.newline()

    # picosvg them
    picosvgs = [rel_build(picosvg_dest(s)) for s in svg_files]
    for svg_file, picosvg in zip(svg_files, picosvgs):
        nw.build(picosvg, "picosvg", svg_file)
    nw.newline()

    # make a glyphmap
    nw.build(
        _COLR2SVG_GLYPHMAP, "write_glyphmap_for_glyph_svgs", picosvgs + [input_font]
    )
    nw.newline()

    # make a config
    nw.build(_COLR2SVG_CONFIG, "write_picosvg_config", input_font)
    nw.newline()

    # generate a new font with SVG glyphs that use the same names as the original
    nw.build(
        "svg_from_colr.ttf",
        "write_svg_font_from_generated_svgs",
        [_COLR2SVG_GLYPHMAP, _COLR2SVG_CONFIG],
    )
    nw.newline()

    # stick our shiny new COLR table onto the input font and declare victory
    nw.build(
        input_font.name,
        "copy_svg_from_colr2svg",
        "svg_from_colr.ttf",
    )
    nw.newline()


def _generate_colr_from_svg(nw: NinjaWriter, input_font: Path, font: ttLib.TTFont):
    # extract the svgs
    svg_extracts = [
        rel_build(svg_extract_dir() / f"{gid:05d}.svg") for gid, _ in svg_glyphs(font)
    ]
    nw.build(svg_extracts, "extract_svgs_from_otsvg", input_font)
    nw.newline()

    # picosvg them
    picosvgs = [rel_build(picosvg_dest(s)) for s in svg_extracts]
    for svg_extract, picosvg in zip(svg_extracts, picosvgs):
        nw.build(picosvg, "picosvg", svg_extract)
    nw.newline()

    # make a glyphmap
    nw.build(
        _SVG2COLR_GLYPHMAP, "write_glyphmap_for_glyph_svgs", picosvgs + [input_font]
    )
    nw.newline()

    # make a config
    nw.build(_SVG2COLR_CONFIG, "write_glyf_colr_1_config", input_font)
    nw.newline()

    # generate a new font with COLR glyphs that use the same names as the original
    nw.build(
        "colr_from_svg.ttf",
        "write_colr_font_from_svg_dump",
        [_SVG2COLR_GLYPHMAP, _SVG2COLR_CONFIG],
    )
    nw.newline()

    # stick our shiny new COLR table onto the input font and declare victory
    nw.build(
        input_font.name,
        "copy_colr_from_svg2colr",
        "colr_from_svg.ttf",
    )
    nw.newline()


def _run(argv):
    if len(argv) != 2:
        raise ValueError("Must have one argument, a font file")

    if not FLAGS.destroy_non_color_glyphs:
        raise NotImplementedError("Retention of non-color glyphs not implemented yet")

    input_font = Path(argv[1])
    assert input_font.is_file()
    font = ttLib.TTFont(input_font)

    build_file = build_dir() / "build.ninja"
    build_dir().mkdir(parents=True, exist_ok=True)

    # TODO flag control instead of guessing
    color_table = _vector_color_table(font)

    if gen_ninja():
        logging.info(f"Generating {build_file.relative_to(build_dir())}")
        input_font = input_font.resolve()  # we need a non-relative path
        with open(build_file, "w") as f:
            nw = NinjaWriter(f)
            _write_preamble(nw, input_font)

            if color_table == "COLR":
                _generate_svg_from_colr(nw, input_font, font)
            else:
                _generate_colr_from_svg(nw, input_font, font)

    maybe_run_ninja(build_file)


def main():
    # We don't seem to be __main__ when run as cli tool installed by setuptools
    app.run(_run)


if __name__ == "__main__":
    app.run(_run)
