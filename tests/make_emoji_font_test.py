# Copyright 2020 Google LLC
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

import sys
from nanoemoji import nanoemoji
import pytest
import test_helper


@pytest.mark.parametrize(
    "filename, codepoints",
    [
        # Noto Emoji, single codepoint
        ("emoji_u1f378.svg", (0x1F378,)),
        # Noto Emoji, multiple codepoints
        ("emoji_u1f385_1f3fb.svg", (0x1F385, 0x1F3FB)),
        # Noto Emoji, lots of codepoints!
        (
            "emoji_u1f469_1f3fd_200d_1f91d_200d_1f468_1f3ff.svg",
            (0x1F469, 0x1F3FD, 0x200D, 0x1F91D, 0x200D, 0x1F468, 0x1F3FF),
        ),
        # Twemoji, single codepoint
        ("2198.svg", (0x2198,)),
        # Twemoji, multiple codepoints
        (
            "1f9d1-200d-1f91d-200d-1f9d1.svg",
            (0x1F9D1, 0x200D, 0x1F91D, 0x200D, 0x1F9D1),
        ),
    ],
)
def test_codepoints_from_filename(filename, codepoints):
    assert codepoints == nanoemoji._codepoints_from_filename(filename)


# TODO test that width, height are removed from svg
# TODO test that enable-background is removed from svg
# TODO test that id=glyph# is added to svg
# TODO test svg compressed false, svgz true

# TODO test round-trip svg => colrv1 => svg


@pytest.mark.parametrize(
    "svg_in, expected_ttx, color_format, output_format",
    [
        # simple fill on rect
        ("rect.svg", "rect_colr_0.ttx", "colr_0", ".ttf"),
        ("rect.svg", "rect_colr_1.ttx", "colr_1", ".ttf"),
        # linear gradient on rect
        ("linear_gradient_rect.svg", "linear_gradient_rect.ttx", "colr_1", ".ttf"),
        # radial gradient on rect
        ("radial_gradient_rect.svg", "radial_gradient_rect.ttx", "colr_1", ".ttf"),
    ],
)
def test_make_emoji_font(svg_in, expected_ttx, color_format, output_format):
    config, glyph_inputs = test_helper.color_font_config(color_format, svg_in, output_format)
    _, ttfont = nanoemoji._generate_color_font(config, glyph_inputs)
    test_helper.assert_expected_ttx(svg_in, ttfont, expected_ttx)
