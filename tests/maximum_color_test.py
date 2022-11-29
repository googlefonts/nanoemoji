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

# Integration tests for nanoemoji.maximum_color

import copy
from fontTools import ttLib
from nanoemoji.keep_glyph_names import keep_glyph_names
from nanoemoji.colr_to_svg import _FOREGROUND_COLOR_INDEX
from picosvg.svg import SVG
from pathlib import Path
import shutil
import pytest
import sys
from test_helper import cleanup_temp_dirs, locate_test_file, run, run_nanoemoji
from typing import Tuple


def _build_initial_font(color_format: str) -> Path:
    tmp_dir = run_nanoemoji(
        (
            "--color_format",
            color_format,
            locate_test_file("emoji_u42.svg"),
        )
    )

    initial_font_file = tmp_dir / "Font.ttf"
    assert initial_font_file.is_file()

    return initial_font_file


def _maximize_color(initial_font_file: Path, additional_flags: Tuple[str, ...]) -> Path:
    # Moar color
    out_dir = initial_font_file.parent / "maximum_color"
    run(
        (
            sys.executable,
            "-m",
            "nanoemoji.maximum_color",
            "--build_dir",
            out_dir,
        )
        + additional_flags
        + (initial_font_file,)
    )

    maxmium_font_file = out_dir / "Font.ttf"
    assert maxmium_font_file.is_file()

    return maxmium_font_file


@pytest.mark.parametrize(
    "input_file",
    [
        "Font.ttf",
        # test that we don't crash when filename contains spaces
        "Color Font.ttf",
    ],
)
@pytest.mark.parametrize(
    "color_format, expected_new_tables",
    [
        ("picosvg", {"COLR", "CPAL"}),
        ("glyf_colr_1", {"SVG "}),
    ],
)
@pytest.mark.parametrize("bitmaps", [True, False])
def test_build_maximum_font(color_format, expected_new_tables, bitmaps, input_file):
    initial_font_file = _build_initial_font(color_format)

    input_file = initial_font_file.parent / input_file
    initial_font_file.rename(input_file)

    bitmap_flag = "--nobitmaps"
    if bitmaps:
        bitmap_flag = "--bitmaps"
        expected_new_tables = copy.copy(expected_new_tables)
        expected_new_tables.update({"CBDT", "CBLC"})

    maxmium_font_file = _maximize_color(input_file, (bitmap_flag,))

    initial_font = ttLib.TTFont(input_file)
    maximum_font = ttLib.TTFont(maxmium_font_file)
    assert set(maximum_font.keys()) - set(initial_font.keys()) == expected_new_tables


@pytest.mark.parametrize("colr_version", [None, 0, 1])
def test_build_colrv0_from_svg(colr_version):
    initial_font_file = _build_initial_font("picosvg")

    additional_flags = ()
    if colr_version is not None:
        additional_flags = ("--colr_version", str(colr_version))

    maxmium_font_file = _maximize_color(initial_font_file, additional_flags)

    initial_font = ttLib.TTFont(initial_font_file)
    maximum_font = ttLib.TTFont(maxmium_font_file)
    assert set(maximum_font.keys()) - set(initial_font.keys()) == {"COLR", "CPAL"}

    expected_version = 1 if colr_version is None else colr_version
    assert maximum_font["COLR"].version == expected_version


@pytest.mark.parametrize("keep_names", [True, False])
def test_keep_glyph_names(keep_names):
    initial_font_file = _build_initial_font("glyf_colr_1")

    # set identifiable glyph names
    font = ttLib.TTFont(initial_font_file)
    keep_glyph_names(font)
    font.setGlyphOrder(["duck_" + gn for gn in font.getGlyphOrder()])
    font.save(initial_font_file)

    keep_glyph_names_flag = "--keep_glyph_names"
    if not keep_names:
        keep_glyph_names_flag = "--nokeep_glyph_names"

    maxmium_font_file = _maximize_color(initial_font_file, (keep_glyph_names_flag,))
    maximum_font = ttLib.TTFont(maxmium_font_file)

    if keep_names:
        assert all(
            gn.startswith("duck_") for gn in maximum_font.getGlyphOrder()
        ), maximum_font.getGlyphOrder()
    else:
        assert all(
            not gn.startswith("duck_") for gn in maximum_font.getGlyphOrder()
        ), maximum_font.getGlyphOrder()


def test_zero_advance_width_colrv1_to_svg():
    tmp_dir = run_nanoemoji(
        (
            "--color_format",
            "glyf_colr_1",
            # use proportional widths, based on viewBox.w
            "--width=0",
            # don't clip to viewBox else zero-width glyph disappears
            "--noclip_to_viewbox",
            locate_test_file("emoji_u42.svg"),
            # this one has viewBox="0 0 0 1200", i.e. zero width, like
            # combining marks usually are (e.g. 'acutecomb')
            locate_test_file("u0301.svg"),
        )
    )

    initial_font_file = tmp_dir / "Font.ttf"
    assert initial_font_file.is_file()

    initial_font = ttLib.TTFont(initial_font_file)
    # sanity check widths are proportional and we have 2 colr glyphs
    assert initial_font["hmtx"]["B"] == (1200, 0)
    assert initial_font["hmtx"]["acutecomb"] == (0, 0)
    assert initial_font["COLR"].table.BaseGlyphList.BaseGlyphCount == 2

    maxmium_font_file = _maximize_color(initial_font_file, ())
    maximum_font = ttLib.TTFont(maxmium_font_file)

    assert "COLR" in maximum_font
    assert maximum_font["COLR"].table.BaseGlyphList.BaseGlyphCount == 2
    assert "SVG " in maximum_font
    assert len(maximum_font["SVG "].docList) == 2

    # check that 'acutecomb' still has 0 advance width
    assert initial_font["hmtx"]["acutecomb"] == (0, 0)
    # it has not been cropped away (has a non-empty bounding box)
    doc = maximum_font["SVG "].docList[1]
    assert doc.startGlyphID == doc.endGlyphID == maximum_font.getGlyphID("acutecomb")
    svg = SVG.fromstring(doc.data)
    shapes = list(svg.shapes())
    assert len(shapes) == 1
    bbox = shapes[0].bounding_box()
    assert bbox.w > 0
    assert bbox.h > 0
    # its bbox matches the respective COLR ClipBox dimensions (quantized to 10)
    clipBox = maximum_font["COLR"].table.ClipList.clips["acutecomb"]
    assert abs(bbox.w - (clipBox.xMax - clipBox.xMin)) <= 10
    assert abs(bbox.h - (clipBox.yMax - clipBox.yMin)) <= 10
    # the SVG shape's horizontal positioning also matches the respective COLR glyph
    assert abs(bbox.x - clipBox.xMin) <= 10


def test_foreground_colr_to_svg_currentColor(tmp_path):
    # Check that COLR 0xFFFF palette index for 'foreground color' gets translated
    # to SVG's fill="currentColor" when maximum_color'ing COLR => OT-SVG
    # https://github.com/googlefonts/nanoemoji/issues/405

    svg_file = tmp_path / "u0041.svg"
    shutil.copyfile(locate_test_file("currentColor.svg"), svg_file)

    run_nanoemoji(("--color_format", "glyf_colr_1", svg_file), tmp_dir=tmp_path)

    initial_font_file = tmp_path / "Font.ttf"
    assert initial_font_file.is_file()
    initial_font = ttLib.TTFont(initial_font_file)

    assert "COLR" in initial_font
    colr = initial_font["COLR"].table
    assert colr.BaseGlyphList.BaseGlyphCount == 1
    assert (
        colr.BaseGlyphList.BaseGlyphPaintRecord[0].Paint.Paint.PaletteIndex
        == _FOREGROUND_COLOR_INDEX
    )

    maxmium_font_file = _maximize_color(initial_font_file, ())
    maximum_font = ttLib.TTFont(maxmium_font_file)

    assert "COLR" in initial_font
    assert "SVG " in maximum_font
    assert len(maximum_font["SVG "].docList) == 1

    assert 'fill="currentColor"' in maximum_font["SVG "].docList[0].data


def test_colr_to_svg_with_colored_notdef(tmp_path):
    initial_font = ttLib.TTFont()
    # this subset of Nabla only contains notdef, space and numbersign
    initial_font.importXML(locate_test_file("fonts/Nabla.subset.ttx"))
    initial_font_file = tmp_path / "Nabla.subset.ttf"
    initial_font.save(initial_font_file)

    maxmium_font_file = _maximize_color(initial_font_file, ())

    maximum_font = ttLib.TTFont(maxmium_font_file)

    # check .notdef glyph is still the first glyph and that space character
    # follows it and has its codepoint assigned in cmap
    assert maximum_font.getGlyphOrder()[:3] == [".notdef", "space", "numbersign"]
    assert maximum_font["cmap"].getBestCmap() == {0x20: "space", ord("#"): "numbersign"}

    # check that SVG table contains a .notdef glyph as GID=0 in a distinct SVG document
    # from the one containing the numbersign
    assert "SVG " in maximum_font
    assert len(maximum_font["SVG "].docList) == 2
    assert maximum_font["SVG "].docList[0].startGlyphID == 0
    assert maximum_font["SVG "].docList[0].startGlyphID == 0
    assert maximum_font["SVG "].docList[1].endGlyphID == 2
    assert maximum_font["SVG "].docList[1].endGlyphID == 2
