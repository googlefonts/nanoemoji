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
from nanoemoji.color_glyph import ColorGlyph
from nanoemoji.paint import *
from nanosvg.svg import SVG
from nanosvg.svg_transform import Affine2D
import os
import pytest
import ufoLib2

# TODO test _glyph_name obeys codepoint order


def _ufo(upem):
    ufo = ufoLib2.Font()
    ufo.info.unitsPerEm = upem
    return ufo


def _test_file(filename):
    return os.path.join(os.path.dirname(__file__), filename)


def _nsvg(filename):
    return SVG.parse(_test_file(filename)).tonanosvg()


@pytest.mark.parametrize(
    "view_box, upem, expected_transform",
    [
        # same upem, flip y
        ("0 0 1024 1024", 1024, Affine2D(1, 0, 0, -1, 0, 1024)),
        # noto emoji norm. scale, flip y
        ("0 0 128 128", 1024, Affine2D(8, 0, 0, -8, 0, 1024)),
        # noto emoji emoji_u26be.svg viewBox. Scale, translate, flip y
        ("-151 297 128 128", 1024, Affine2D(8, 0, 0, -8, 1208, -1352)),
        # made up example. Scale, translate, flip y
        (
            "10 11 20 21",
            100,
            Affine2D(a=5.0, b=0, c=0, d=-4.761905, e=-50.0, f=47.619048),
        ),
    ],
)
def test_transform(view_box, upem, expected_transform):
    svg_str = (
        '<svg version="1.1"'
        ' xmlns="http://www.w3.org/2000/svg"'
        f' viewBox="{view_box}"'
        "/>"
    )
    color_glyph = ColorGlyph.create(
        _ufo(upem), "duck", 1, [0x0042], SVG.fromstring(svg_str)
    )

    assert color_glyph.transform_for_font_space() == pytest.approx(expected_transform)


@pytest.mark.parametrize(
    "svg_in, expected_paints",
    [
        # solid
        (
            "rect.svg",
            {
                PaintSolid(color=Color.fromstring("blue")),
                PaintSolid(color=Color.fromstring("blue", alpha=0.8)),
            },
        ),
        # linear
        (
            "linear_gradient_rect.svg",
            {
                PaintLinearGradient(
                    stops=(
                        ColorStop(stopOffset=0.1, color=Color.fromstring("blue")),
                        ColorStop(stopOffset=0.9, color=Color.fromstring("cyan")),
                    ),
                    p0=Point(200, 800),
                    p1=Point(800, 800),
                )
            },
        ),
        # radial
        (
            "radial_gradient_rect.svg",
            {
                PaintRadialGradient(
                    extend=Extend.REPEAT,
                    stops=(
                        ColorStop(stopOffset=0.05, color=Color.fromstring("fuchsia")),
                        ColorStop(stopOffset=0.75, color=Color.fromstring("orange")),
                    ),
                    c0=Point(500, 700),
                    c1=Point(500, 700),
                    r0=0,
                    r1=300,
                    affine2x2=(1.0, 0.0, 0.0, -0.33333333333333337),
                )
            },
        ),
        # TODO gradientTransform => affine2x2
    ],
)
def test_paint_from_shape(svg_in, expected_paints):
    color_glyph = ColorGlyph.create(_ufo(1000), "duck", 1, [0x0042], _nsvg(svg_in))
    assert color_glyph.paints() == expected_paints
