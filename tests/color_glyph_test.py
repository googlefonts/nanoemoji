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
from picosvg.svg import SVG
from picosvg.svg_transform import Affine2D
import os
import dataclasses
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
    return SVG.parse(_test_file(filename)).topicosvg()


@pytest.mark.parametrize(
    "view_box, upem, expected_transform",
    [
        # same upem, flip y
        ("0 0 1024 1024", 1024, Affine2D(1, 0, 0, -1, 0, 1024)),
        # noto emoji norm. scale, flip y
        ("0 0 128 128", 1024, Affine2D(8, 0, 0, -8, 0, 1024)),
        # noto emoji emoji_u26be.svg viewBox. Scale, flip y and translate
        ("-151 297 128 128", 1024, Affine2D(8, 0, 0, -8, 1208, 3400)),
        # made up example. Scale, translate, flip y
        (
            "10 11 20 21",
            100,
            Affine2D(a=5.0, b=0, c=0, d=-4.761905, e=-50.0, f=152.380952),
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


def _round_gradient_coordinates(paint, prec=6):
    # We can't use dataclasses.replace() below because of a bug in the
    # dataclasses backport for python 3.6:
    # https://github.com/ericvsmith/dataclasses/issues/143
    if isinstance(paint, PaintLinearGradient):
        return PaintLinearGradient(
            extend=paint.extend,
            stops=paint.stops,
            p0=Point(round(paint.p0.x, prec), round(paint.p0.y, prec)),
            p1=Point(round(paint.p1.x, prec), round(paint.p1.y, prec)),
            p2=Point(round(paint.p2.x, prec), round(paint.p2.y, prec)),
        )
    elif isinstance(paint, PaintRadialGradient):
        return PaintRadialGradient(
            extend=paint.extend,
            stops=paint.stops,
            c0=Point(round(paint.c0.x, prec), round(paint.c0.y, prec)),
            c1=Point(round(paint.c1.x, prec), round(paint.c1.y, prec)),
            r0=round(paint.r0, prec),
            r1=round(paint.r1, prec),
            affine2x2=(
                tuple(round(v, prec) for v in paint.affine2x2)
                if paint.affine2x2 is not None
                else None
            ),
        )
    else:
        return paint


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
                        ColorStop(stopOffset=0.9, color=Color.fromstring("cyan", 0.8)),
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
                    affine2x2=(1.0, 0.0, 0.0, -0.333333),
                )
            },
        ),
        # radial with gradientTransform
        (
            "radial_gradient_transform.svg",
            {
                PaintRadialGradient(
                    stops=(
                        ColorStop(stopOffset=0.0, color=Color.fromstring("darkblue")),
                        ColorStop(stopOffset=0.5, color=Color.fromstring("skyblue")),
                        ColorStop(stopOffset=1.0, color=Color.fromstring("darkblue")),
                    ),
                    c0=Point(x=506.985117, y=500.0),
                    c1=Point(x=506.985117, y=500.0),
                    r0=0,
                    r1=500,
                    affine2x2=(1.0, 0.0, 0.36397, -1.0),
                )
            },
        ),
        # linear with gradientTransform
        (
            "linear_gradient_transform.svg",
            {
                PaintLinearGradient(
                    extend=Extend.REFLECT,
                    stops=(
                        ColorStop(stopOffset=0.0, color=Color.fromstring("green")),
                        ColorStop(stopOffset=0.5, color=Color.fromstring("white")),
                        ColorStop(stopOffset=1.0, color=Color.fromstring("red")),
                    ),
                    p0=Point(x=0, y=1000),
                    p1=Point(x=1000, y=1000),
                    p2=Point(x=500, y=500),
                )
            },
        ),
        # linear with both gradientTransform and objectBoundingBox
        (
            "linear_gradient_transform_2.svg",
            {
                PaintLinearGradient(
                    stops=(
                        ColorStop(stopOffset=0.05, color=Color.fromstring("gold")),
                        ColorStop(stopOffset=0.95, color=Color.fromstring("red")),
                    ),
                    p0=Point(x=100, y=550),
                    p1=Point(x=900, y=550),
                ),
                PaintLinearGradient(
                    stops=(
                        ColorStop(stopOffset=0.05, color=Color.fromstring("gold")),
                        ColorStop(stopOffset=0.95, color=Color.fromstring("red")),
                    ),
                    p0=Point(x=450, y=900),
                    p1=Point(x=450, y=100),
                ),
            },
        ),
        # radial with gradientTransform with almost zero scale, non-zero skew
        (
            "radial_gradient_transform_2.svg",
            {
                PaintRadialGradient(
                    stops=(
                        ColorStop(stopOffset=0.0, color=Color.fromstring("white"),),
                        ColorStop(stopOffset=1.0, color=Color.fromstring("black"),),
                    ),
                    c0=Point(x=280.284146, y=973.125),
                    c1=Point(x=280.284146, y=973.125),
                    r0=0.0,
                    r1=129.015625,
                    affine2x2=(0.0, -1.0, -0.9288, 0.0),
                )
            },
        ),
        # Shape with opacity, should apply to gradient colors
        # See https://github.com/googlefonts/picosvg/issues/76
        (
            "gradient_opacity.svg",
            {
                PaintLinearGradient(
                    stops=(
                        ColorStop(stopOffset=0.1, color=Color.fromstring("blue", alpha=0.4)),
                        ColorStop(stopOffset=0.9, color=Color.fromstring("cyan", alpha=0.4 * 0.8)),
                    ),
                    p0=Point(200.0, 800.0),
                    p1=Point(800.0, 800.0),
                ),
                PaintRadialGradient(
                    stops=(
                        ColorStop(stopOffset=0.1, color=Color.fromstring("red", alpha=0.5),),
                        ColorStop(stopOffset=0.9, color=Color.fromstring("yellow", alpha=0.5 * 0.8),),
                    ),
                    c0=Point(x=500.0, y=400.0),
                    c1=Point(x=500.0, y=400.0),
                    r0=0.0,
                    r1=300.0,
                    affine2x2=(1.0, 0.0, 0.0, -0.333333),
                )
            },
        ),
    ],
)
def test_paint_from_shape(svg_in, expected_paints):
    color_glyph = ColorGlyph.create(_ufo(1000), "duck", 1, [0x0042], _nsvg(svg_in))
    assert {
        _round_gradient_coordinates(paint) for paint in color_glyph.paints()
    } == expected_paints


# TODO test that a composite is NOT formed where paint changes
