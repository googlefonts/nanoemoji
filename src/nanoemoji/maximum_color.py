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

python -m nanoemoji.maximum_color MySvgFont.ttf"""
from absl import app
from absl import logging
from fontTools import ttLib
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


def _vector_color_table(font: ttLib.TTFont) -> str:
    has_svg = "SVG " in font
    has_colr = "COLR" in font
    if has_svg == has_colr:
        raise ValueError("Must have one of COLR, SVG")

    if has_svg:
        return "SVG "
    if has_colr:
        return "COLR"

    raise ValueError("Impossible")


def svg_extract_dir() -> Path:
    return build_dir() / "svg_dump"


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

    module_rule(nw, "write_glyphmap_for_glyph_svgs", "--output_file $out $in")
    nw.newline()

    module_rule(nw, "write_config_for_glyph_svgs", "$in $out")
    nw.newline()

    module_rule(
        nw,
        "write_font",
        f"--glyphmap_file {_SVG2COLR_GLYPHMAP} --config_file {_SVG2COLR_CONFIG} --output_file $out",
        rule_name="write_colr_font_from_svg_dump",
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
        f"--color_table COLR --target_font {rel_build(input_font)} --donor_font $in --output_file $out",
        rule_name="copy_colr_from_svg2colr",
    )
    nw.newline()


def _write_svg_extract(nw: NinjaWriter, input_font: Path, font: ttLib.TTFont):
    # extract the svgs
    svg_extracts = [
        rel_build(svg_extract_dir() / f"{gid}.svg") for gid, _ in svg_glyphs(font)
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
    nw.build(_SVG2COLR_CONFIG, "write_config_for_glyph_svgs", input_font)
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


def main(argv):
    if len(argv) != 2:
        raise ValueError("Must have one argument, a font file")

    input_font = Path(argv[1])
    assert input_font.is_file()
    font = ttLib.TTFont(input_font)

    build_file = build_dir() / "build.ninja"
    build_dir().mkdir(parents=True, exist_ok=True)

    color_table = _vector_color_table(font)

    if gen_ninja():
        logging.info(f"Generating {build_file.relative_to(build_dir())}")
        with open(build_file, "w") as f:
            nw = NinjaWriter(f)
            _write_preamble(nw, input_font)

            if color_table == "COLR":
                raise NotImplementedError("Conversion from COLR coming soon")
            else:
                _write_svg_extract(nw, input_font, font)

    maybe_run_ninja(build_file)


if __name__ == "__main__":
    app.run(main)
