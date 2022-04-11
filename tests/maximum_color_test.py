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
from pathlib import Path
import pytest
import sys
from test_helper import cleanup_temp_dirs, locate_test_file, run, run_nanoemoji
from typing import Tuple


@pytest.fixture(scope="module", autouse=True)
def _cleanup_temporary_dirs():
    # The mkdtemp() docs say the user is responsible for deleting the directory
    # and its contents when done with it. So we use an autouse fixture that
    # automatically removes all the temp dirs at the end of the test module
    yield
    # teardown happens after the 'yield'
    cleanup_temp_dirs()


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
    "color_format, expected_new_tables",
    [
        ("picosvg", {"COLR", "CPAL"}),
        ("glyf_colr_1", {"SVG "}),
    ],
)
@pytest.mark.parametrize("bitmaps", [True, False])
def test_build_maximum_font(color_format, expected_new_tables, bitmaps):
    initial_font_file = _build_initial_font(color_format)

    bitmap_flag = "--nobitmaps"
    if bitmaps:
        bitmap_flag = "--bitmaps"
        expected_new_tables = copy.copy(expected_new_tables)
        expected_new_tables.update({"CBDT", "CBLC"})

    maxmium_font_file = _maximize_color(initial_font_file, (bitmap_flag,))

    initial_font = ttLib.TTFont(initial_font_file)
    maximum_font = ttLib.TTFont(maxmium_font_file)
    assert set(maximum_font.keys()) - set(initial_font.keys()) == expected_new_tables


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
