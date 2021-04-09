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

from nanoemoji.colors import Color
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
    ],
)
def test_color_to_string(color, expected_string):
    assert expected_string == color.to_string()
