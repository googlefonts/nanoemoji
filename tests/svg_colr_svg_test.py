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

import pytest
import test_helper
from picosvg.svg import SVG
from nanoemoji import write_font
from colr_to_svg import colr_to_svg


# TODO otf test
@pytest.mark.parametrize(
    "svg_in, expected_svg_out, color_format, output_format",
    [
        # simple fill on rect
        ("rect.svg", "rect_from_colr_0.svg", "glyf_colr_0", ".ttf"),
        ("rect.svg", "rect_from_colr_1.svg", "glyf_colr_1", ".ttf"),
        # linear gradient on rect
        (
            "linear_gradient_rect.svg",
            "linear_gradient_rect_from_colr_1.svg",
            "glyf_colr_1",
            ".ttf",
        ),
        # radial gradient on rect
        (
            "radial_gradient_rect.svg",
            "radial_gradient_rect_from_colr_1.svg",
            "glyf_colr_1",
            ".ttf",
        ),
    ],
)
def test_svg_to_colr_to_svg(svg_in, expected_svg_out, color_format, output_format):
    config, glyph_inputs = test_helper.color_font_config(
        color_format, (svg_in,), output_format
    )
    _, ttfont = write_font._generate_color_font(config, glyph_inputs)
    svg_before = test_helper.picosvg(svg_in, locate=True)
    svgs_from_font = tuple(colr_to_svg(svg_before.view_box(), ttfont).values())
    assert len(svgs_from_font) == 1
    test_helper.svg_diff(
        svgs_from_font[0], test_helper.picosvg(expected_svg_out, locate=True)
    )
