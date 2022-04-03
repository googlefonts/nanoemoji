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

Use cbdt for bitmaps because sbix is less x-platform than you'd guess
(https://github.com/harfbuzz/harfbuzz/issues/2679)

Sample usage:

maximum_color MySvgFont.ttf"""
from absl import app
from absl import flags
from absl import logging
from fontTools import ttLib
from fontTools.ttLib.ttFont import newTable
from nanoemoji import config
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
from typing import List, NamedTuple, Tuple


FLAGS = flags.FLAGS


flags.DEFINE_bool(
    "destroy_non_color_glyphs",
    True,
    "If true feel free to obliterate any existing glyf/cff content, e.g. fallback glyphs",
)
flags.DEFINE_bool(
    "bitmaps",
    False,
    "If true, generate a bitmap table (specificaly CBDT)",
)


# attribute names need to match inputs to write_font rule
class WriteFontInputs(NamedTuple):
    glyphmap_file: Path
    config_file: Path

    @property
    def table_tag(self) -> str:
        return f"{Path(self.glyphmap_file).stem:4}"

    @property
    def color_format(self) -> str:
        identifier = self.table_tag.strip().lower()

        if identifier == "svg":
            # for good woff2 performance, at cost of inflated size
            return "picosvg"
        elif identifier == "colr":
            # optimize for woff2 performance
            return "glyf_colr_1"
        elif identifier == "cbdt":
            return "cbdt"
        else:
            raise ValueError(f"What is {identifier}?!")

    @classmethod
    def for_tag(cls, table_tag: str) -> "WriteFontInputs":
        basename = table_tag.strip()
        return cls(Path(basename + ".glyphmap"), Path(basename + ".toml"))


def _vector_color_table(font: ttLib.TTFont) -> str:
    has_svg = "SVG " in font
    has_colr = "COLR" in font
    if has_svg == has_colr:
        raise ValueError("Must have exactly one of COLR, SVG")

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


def bitmap_dir() -> Path:
    return build_dir() / "bitmap"


def bitmap_dest(input_svg: Path) -> Path:
    return bitmap_dir() / input_svg.with_suffix(".png").name


def _write_preamble(nw: NinjaWriter):
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
        "--color_format $color_format $in $out",
    )
    nw.newline()

    module_rule(
        nw,
        "write_font",
        f"--glyphmap_file $glyphmap_file --config_file $config_file --output_file $out",
    )
    nw.newline()

    nw.rule(
        f"picosvg",
        f"picosvg --output_file $out $in",
    )
    nw.newline()

    # set height only, let width scale proportionally
    res = config.load().bitmap_resolution
    nw.rule(
        "write_bitmap",
        f"resvg -h {res} $in $out",
    )
    nw.newline()

    module_rule(
        nw,
        "glue_together",
        f"--color_table $color_table --target_font $target_font --donor_font $in --output_file $out",
    )
    nw.newline()

    module_rule(
        nw,
        "keep_glyph_names",
        f"$in $out",
    )
    nw.newline()

    module_rule(
        nw,
        "strip_glyph_names",
        f"$in $out",
    )
    nw.newline()

    module_rule(
        nw,
        "copy",
        f"$in $out",
    )
    nw.newline()


def _write_font(nw: NinjaWriter, output_file: Path, inputs: WriteFontInputs):
    nw.build(
        output_file, "write_font", implicit=list(inputs), variables=inputs._asdict()
    )
    nw.newline()


def _write_config_for_mergeable(
    nw: NinjaWriter, config_file: Path, input_font: Path, color_format: str
):
    nw.build(
        config_file,
        "write_config_for_mergeable",
        input_font,
        variables={"color_format": color_format},
    )
    nw.newline()


def _picosvgs(nw: NinjaWriter, svg_files: List[Path]) -> List[Path]:
    picosvgs = [rel_build(picosvg_dest(s)) for s in svg_files]
    for svg_file, picosvg in zip(svg_files, picosvgs):
        nw.build(picosvg, "picosvg", svg_file)
    nw.newline()
    return picosvgs


def _generate_additional_color_table(
    nw: NinjaWriter,
    input_font: Path,
    glyphmap_inputs: List[Path],
    table_tag: str,
    glue_target: Path,
) -> Path:
    write_font_inputs = WriteFontInputs.for_tag(table_tag)
    identifier = write_font_inputs.color_format
    del table_tag

    # make a glyphmap
    nw.build(
        write_font_inputs.glyphmap_file,
        "write_glyphmap_for_glyph_svgs",
        glyphmap_inputs,
    )
    nw.newline()

    # picosvg because we want good woff2 outcomes
    _write_config_for_mergeable(
        nw, write_font_inputs.config_file, input_font, write_font_inputs.color_format
    )

    # generate a new font with SVG glyphs that use the same names as the original
    font_with_new_table = Path("MergeSource." + identifier + ".ttf")
    _write_font(nw, font_with_new_table, write_font_inputs)

    # stick our shiny new table onto the input font
    output_file = Path(input_font.stem + f".added_{identifier}.ttf")
    nw.build(
        output_file,
        "glue_together",
        font_with_new_table,
        implicit=list({input_font, glue_target}),
        variables={
            "color_table": write_font_inputs.table_tag.strip(),
            "target_font": glue_target,
        },
    )
    nw.newline()

    return output_file


def _generate_svg_from_colr(
    nw: NinjaWriter, input_font: Path, font: ttLib.TTFont
) -> Tuple[Path, List[Path]]:
    # generate svgs
    svg_files = [
        rel_build(svg_generate_dir() / f"{gid:05d}.svg") for gid in colr_glyphs(font)
    ]
    nw.build(svg_files, "generate_svgs_from_colr", input_font)
    nw.newline()

    # create and merge an SVG table
    picosvgs = _picosvgs(nw, svg_files)
    output_file = _generate_additional_color_table(
        nw, input_font, picosvgs + [input_font], "SVG ", input_font
    )
    return output_file, picosvgs


def _generate_colr_from_svg(
    nw: NinjaWriter, input_font: Path, font: ttLib.TTFont
) -> Tuple[Path, List[Path]]:
    # extract the svgs
    svg_files = [
        rel_build(svg_extract_dir() / f"{gid:05d}.svg") for gid, _ in svg_glyphs(font)
    ]
    nw.build(svg_files, "extract_svgs_from_otsvg", input_font)
    nw.newline()

    # create and merge a COLR table
    picosvgs = _picosvgs(nw, svg_files)
    output_file = _generate_additional_color_table(
        nw, input_font, picosvgs + [input_font], "COLR", input_font
    )
    return output_file, picosvgs


def _generate_cbdt(
    nw: NinjaWriter,
    input_font: Path,
    font: ttLib.TTFont,
    color_font: Path,
    picosvg_files: List[Path],
):
    # generate bitmaps
    bitmap_files = [rel_build(bitmap_dest(s)) for s in picosvg_files]
    for picosvg, bitmap in zip(picosvg_files, bitmap_files):
        nw.build(bitmap, "write_bitmap", picosvg)
    nw.newline()

    # create and merge a COLR table
    output_file = _generate_additional_color_table(
        nw, input_font, picosvg_files + bitmap_files + [input_font], "CBDT", color_font
    )
    return output_file


def _keep_glyph_names(nw: NinjaWriter, input_file: Path) -> ttLib.TTFont:
    # The whole concept is we keep glyph name stable until the end so
    # make sure we start with stable names. Doesn't matter what they are,
    # just that they don't change.
    output_file = Path(input_file.stem + ".keep_glyph_names.ttf")
    nw.build(
        output_file,
        "keep_glyph_names",
        input_file,
    )
    nw.newline()
    return output_file


def _strip_glyph_names(nw: NinjaWriter, input_file: Path, output_file: Path):
    nw.build(
        output_file,
        "strip_glyph_names",
        input_file,
    )
    nw.newline()


def _run(argv):
    if len(argv) != 2:
        raise ValueError("Must have one argument, a font file")

    if not FLAGS.destroy_non_color_glyphs:
        raise NotImplementedError("Retention of non-color glyphs not implemented yet")

    input_file = Path(argv[1]).resolve()  # we need a non-relative path
    assert input_file.is_file()
    font = ttLib.TTFont(input_file)
    final_output = Path(config.load().output_file)
    assert (
        input_file.resolve() != (build_dir() / final_output).resolve()
    ), "In == Out is bad"

    build_file = build_dir() / "build.ninja"
    build_dir().mkdir(parents=True, exist_ok=True)

    color_table = _vector_color_table(font)

    if gen_ninja():
        logging.info(f"Generating {build_file.relative_to(build_dir())}")
        with open(build_file, "w") as f:
            nw = NinjaWriter(f)
            _write_preamble(nw)

            wip_file = _keep_glyph_names(nw, input_file)

            # generate the missing vector table
            if color_table == "COLR":
                wip_file, picosvg_files = _generate_svg_from_colr(nw, wip_file, font)
            else:
                wip_file, picosvg_files = _generate_colr_from_svg(nw, wip_file, font)

            if FLAGS.bitmaps:
                wip_file = _generate_cbdt(nw, input_file, font, wip_file, picosvg_files)

            if config.load().keep_glyph_names:
                nw.build(final_output, "copy", wip_file)
            else:
                _strip_glyph_names(nw, wip_file, final_output)

    maybe_run_ninja(build_file)


def main():
    # We don't seem to be __main__ when run as cli tool installed by setuptools
    app.run(_run)


if __name__ == "__main__":
    app.run(_run)
