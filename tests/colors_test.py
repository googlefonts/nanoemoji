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

from nanoemoji.colors import Color, uniq_sort_cpal_colors
import pytest


@pytest.mark.parametrize(
    "color_string, expected_color",
    [
        # 3-hex digits
        ("#BCD", Color(0xBB, 0xCC, 0xDD, 1.0)),
        # 4-hex digits
        ("#BCD3", Color(0xBB, 0xCC, 0xDD, 0.2)),
        # 6-hex digits
        ("#F1E2D3", Color(0xF1, 0xE2, 0xD3, 1.0)),
        # 8-hex digits
        ("#F1E2D366", Color(0xF1, 0xE2, 0xD3, 0.4)),
        # CSS named color
        ("wheat", Color(0xF5, 0xDE, 0xB3, 1.0)),
        # rgb(r,g,b)
        ("rgb(0, 256, -1)", Color(0, 255, 0, 1.0)),
        # rgb(r g b)
        ("rgb(42 101 43)", Color(42, 101, 43, 1.0)),
        # extra whitespace as found in the noto-emoji Luxembourg flag
        ("#00A1DE\n", Color(0, 161, 222, 1.0)),
        # 'currentColor' is a special keyword
        ("currentColor", Color(-1, -1, -1, 1.0)),
        # CSS variables for CPAL palette entry indices
        ("var(--color0, red)", Color(255, 0, 0, 1.0, palette_index=0)),
        ("var(--color123, #ABCDEF)", Color(0xAB, 0xCD, 0xEF, 1.0, palette_index=123)),
        # CSS variables with funky whitespace
        ("  var\t  ( --color1 ,   yellow ) ", Color(255, 255, 0, 1.0, palette_index=1)),
    ],
)
def test_color_fromstring(color_string, expected_color):
    assert expected_color == Color.fromstring(color_string)


@pytest.mark.parametrize(
    "color, expected_string",
    [
        # 3-hex digits
        (Color(0xBB, 0xCC, 0xDD, 1.0), "#BBCCDD"),
        # 6-hex digits
        (Color(0xF1, 0xE2, 0xD3, 1.0), "#F1E2D3"),
        # 8-hex digits
        (Color(0xF1, 0xE2, 0xD3, 0.4), "#F1E2D366"),
        # CSS named color
        (Color(0xF5, 0xDE, 0xB3, 1.0), "wheat"),
        # CSS named color skipped for alpha != 1
        (Color(0xF5, 0xDE, 0xB3, 0.4), "#F5DEB366"),
        # special sentinel value that stands for 'currentColor' keyword
        (Color(-1, -1, -1, 1.0), "currentColor"),
        # CSS var(--color{palette_index]) when palette_index is not None
        (Color(255, 0, 0, 1.0, palette_index=0), "var(--color0, red)"),
        (Color(0xAB, 0xCD, 0xEF, 1.0, palette_index=123), "var(--color123, #ABCDEF)"),
    ],
)
def test_color_to_string(color, expected_string):
    assert expected_string == color.to_string()


def test_color_like_namedtuple():
    color = Color(0x00, 0x11, 0x22, 1.0, 4)

    assert color.red == color[0] == 0x00
    assert color.green == color[1] == 0x11
    assert color.blue == color[2] == 0x22
    assert color.alpha == color[3] == 1.0
    assert color.palette_index == color[4] == 4

    assert len(color) == 5

    assert tuple(color) == (0x00, 0x11, 0x22, 1.0, 4)

    assert color[:3] == (0x00, 0x11, 0x22)

    assert color._replace(palette_index=5) == Color(0x00, 0x11, 0x22, 1.0, 5)


@pytest.mark.parametrize(
    "colors, expected",
    [
        # empty CPAL is filled with no-op color, or else Chrome rejects it
        pytest.param([], [Color(0, 0, 0, 1.0)], id="empty"),
        # colors with explicit palette_index are sorted accordingly
        pytest.param(
            [
                Color(255, 0, 0, 1.0, palette_index=1),
                Color(0, 255, 0, 1.0, palette_index=0),
            ],
            [
                Color(0, 255, 0, 1.0, palette_index=0),
                Color(255, 0, 0, 1.0, palette_index=1),
            ],
            id="keep-orig-index",
        ),
        # same color can appear with different indices (not viceversa)
        pytest.param(
            [
                Color(255, 0, 0, 1.0, palette_index=0),
                Color(255, 0, 0, 1.0, palette_index=1),
            ],
            [
                Color(255, 0, 0, 1.0, palette_index=0),
                Color(255, 0, 0, 1.0, palette_index=1),
            ],
            id="no-dedup-indexed",
        ),
        # duplicate unpalette_indexed colors are made unique
        pytest.param(
            [Color(255, 0, 0, 1.0), Color(255, 0, 0, 1.0)],
            [Color(255, 0, 0, 1.0)],
            id="dedup-unindexed",
        ),
        # unindexed colors are placed in empty slots, sorted by > RGBA
        pytest.param(
            [
                Color(0, 0, 0, 1.0, palette_index=1),
                Color(0xFF, 0xFF, 0xFF, 1.0, palette_index=3),
                Color(2, 2, 2, 1.0),
                Color(1, 1, 1, 1.0),
                Color(3, 3, 3, 1.0),
            ],
            [
                Color(1, 1, 1, 1.0),
                Color(0, 0, 0, 1.0, palette_index=1),
                Color(2, 2, 2, 1.0),
                Color(0xFF, 0xFF, 0xFF, 1.0, palette_index=3),
                Color(3, 3, 3, 1.0),
            ],
            id="fill-empty-slots",
        ),
        # unindexed color are never conflated with those with an explicit index
        # even if == RGBA value, for selecting a different palette should not
        # inadvertently affect colors that weren't explicitly assigned an index
        pytest.param(
            [
                Color(0xFF, 0, 0, 1.0),
                Color(0xFF, 0, 0, 1.0, palette_index=0),
            ],
            [
                Color(0xFF, 0, 0, 1.0, palette_index=0),
                Color(0xFF, 0, 0, 1.0),
            ],
            id="keep-unindexed-distinct",
        ),
    ],
)
def test_uniq_sort_cpal_colors(colors, expected):
    assert uniq_sort_cpal_colors(colors) == expected


def test_uniq_sort_cpal_colors_ambiguous_indices():
    with pytest.raises(ValueError, match="Palette entry 1 already maps to"):
        uniq_sort_cpal_colors(
            [
                Color(0, 0, 0, 1.0, palette_index=0),
                Color(0x80, 0, 0, 1.0, palette_index=1),
                Color(0, 0, 0, 1.0, palette_index=0),
                Color(0, 0x80, 0, 1.0, palette_index=1),
            ]
        )
