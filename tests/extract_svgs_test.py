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

# Tests for extract_svgs.py


from fontTools import ttLib
from nanoemoji.extract_svgs import svg_glyphs, _remove_glyph_elements
from picosvg.svg import SVG
import pytest
from test_helper import cleanup_temp_dirs, locate_test_file, run_nanoemoji


@pytest.fixture(scope="module", autouse=True)
def _cleanup_temporary_dirs():
    # The mkdtemp() docs say the user is responsible for deleting the directory
    # and its contents when done with it. So we use an autouse fixture that
    # automatically removes all the temp dirs at the end of the test module
    yield
    # teardown happens after the 'yield'
    cleanup_temp_dirs()


def test_find_svg_ids():
    # make a simple svg font
    tmp_dir = run_nanoemoji(
        (
            "--color_format",
            "picosvg",
            locate_test_file("emoji_u42.svg"),
        )
    )
    font_file = tmp_dir / "Font.ttf"
    assert font_file.is_file()

    gids = set()
    font = ttLib.TTFont(font_file)
    for gid, raw_svg in svg_glyphs(font):
        gids.add(gid)

    assert len(gids) == 1
    assert font["cmap"].getBestCmap()[0x42] == font.getGlyphName(next(iter(gids)))


@pytest.mark.parametrize(
    "initial_svg, gids_to_remove, expected_result",
    [
        # remove nothing from an svg that has only one glyph
        ("otsvg_bungee_style.svg", set(), "otsvg_bungee_style.svg"),
        # remove all but one from a nanoemoji-style multi-glyph svg
        ("otsvg_nanoemoji_style.svg", {2, 3}, "otsvg_nanoemoji_style_glyph4.svg"),
    ],
)
def test_remove_glyph_elements(initial_svg, gids_to_remove, expected_result):
    initial_svg = locate_test_file(initial_svg)
    expected_result = locate_test_file(expected_result)
    actual_result = _remove_glyph_elements(
        SVG.parse(initial_svg), gids_to_remove
    ).tostring(pretty_print=True)
    expected_result = SVG.parse(expected_result).tostring(pretty_print=True)
    assert expected_result == actual_result
