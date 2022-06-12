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
from picosvg.svg_meta import ntos
from picosvg.svg_transform import Affine2D
from nanoemoji import write_font
from nanoemoji.colr_to_svg import colr_to_svg


# TODO otf test
@pytest.mark.parametrize(
    "svg_in, expected_svg_out, config_overrides",
    [
        # simple fill on rect
        ("rect.svg", "rect_from_colr_0.svg", {"color_format": "glyf_colr_0"}),
        ("rect.svg", "rect_from_colr_1.svg", {"color_format": "glyf_colr_1"}),
        # linear gradient on rect
        (
            "linear_gradient_rect.svg",
            "linear_gradient_rect_from_colr_1.svg",
            {"color_format": "glyf_colr_1"},
        ),
        # radial gradient on rect
        (
            "radial_gradient_rect.svg",
            "radial_gradient_rect_from_colr_1.svg",
            {"color_format": "glyf_colr_1"},
        ),
        # https://github.com/googlefonts/nanoemoji/issues/327: PaintComposite
        (
            "group_opacity.svg",
            "group_opacity_from_colr_1.svg",
            {"color_format": "glyf_colr_1"},
        ),
        # Roundtrip SVG containing reused shapes with gradients
        # https://github.com/googlefonts/nanoemoji/issues/334
        (
            "reused_shape_with_gradient.svg",
            "reused_shape_with_gradient_from_colr_1.svg",
            {
                "color_format": "glyf_colr_1",
                # test_helper's default upem=100 is too coarse for glyf integer
                # coordinates to approximate circles with quadratic beziers, hence
                # we make it bigger below
                "upem": 1024,
                "width": 1275,
                "ascender": 950,
                "descender": -250,
            },
        ),
        # Roundtrip a narrow svg, retaining proportion
        (
            "square_vbox_narrow.svg",
            "square_vbox_narrow_from_colr_1.svg",
            {
                "width": 0,
            },
        ),
        # Roundtrip a square svg, retaining proportion
        (
            "square_vbox_square.svg",
            "square_vbox_square_from_colr_1.svg",
            {
                "width": 0,
            },
        ),
        # Roundtrip a wide svg, retaining proportion
        (
            "square_vbox_wide.svg",
            "square_vbox_wide_from_colr_1.svg",
            {
                "width": 0,
            },
        ),
    ],
)
def test_svg_to_colr_to_svg(svg_in, expected_svg_out, config_overrides):
    config, parts, glyph_inputs = test_helper.color_font_config(
        config_overrides,
        (svg_in,),
    )
    parts.compute_donors()

    _, ttfont = write_font._generate_color_font(config, parts, glyph_inputs)
    svg_before = SVG.parse(str(test_helper.locate_test_file(svg_in)))

    svgs_from_font = tuple(
        colr_to_svg(
            lambda _: parts.view_box,
            lambda _: svg_before.view_box(),
            ttfont,
            rounding_ndigits=3,
        ).values()
    )
    assert len(svgs_from_font) == 1
    svg_expected = SVG.parse(str(test_helper.locate_test_file(expected_svg_out)))
    test_helper.svg_diff(svgs_from_font[0], svg_expected)
