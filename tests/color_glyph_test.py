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
from nanoemoji.config import FontConfig
from nanoemoji.paint import *
from picosvg.svg import SVG
from picosvg.svg_transform import Affine2D
import dataclasses
import io
import os
import pprint
import pytest
import ufoLib2

# TODO test _glyph_name obeys codepoint order


def _ufo(config):
    ufo = ufoLib2.Font()
    ufo.info.unitsPerEm = config.upem
    ufo.info.ascender = config.ascender
    ufo.info.descender = config.descender
    return ufo


def _test_file(filename):
    return os.path.join(os.path.dirname(__file__), filename)


def _nsvg(filename):
    return SVG.parse(_test_file(filename)).topicosvg()


def _pprint(thing):
    stream = io.StringIO()
    pprint.pprint(thing, indent=2, stream=stream)
    return stream.getvalue()


@pytest.mark.parametrize(
    "view_box, upem, width, ascender, descender, expected_transform, expected_width",
    [
        # same upem, flip y
        ("0 0 1024 1024", 1024, 1024, 1024, 0, Affine2D(1, 0, 0, -1, 0, 1024), 1024),
        # noto emoji norm. scale, flip y
        ("0 0 128 128", 1024, 1024, 1024, 0, Affine2D(8, 0, 0, -8, 0, 1024), 1024),
        # noto emoji emoji_u26be.svg viewBox. Scale, flip y and translate
        (
            "-151 297 128 128",
            1024,
            1024,
            1024,
            0,
            Affine2D(8, 0, 0, -8, 1208, 3400),
            1024,
        ),
        # made up example. Scale, translate, flip y, center horizontally
        (
            "10 11 20 21",
            100,
            100,
            100,
            0,
            Affine2D(a=4.761905, b=0, c=0, d=-4.761905, e=-45.238095, f=152.380952),
            100,
        ),
        # noto emoji width, ascender, descender
        (
            "0 0 1024 1024",
            1024,
            1275,
            950,
            -250,
            Affine2D(1.171875, 0, 0, -1.171875, 37.5, 950),
            1275,
        ),
        # wider than tall: uniformly scale by height and stretch advance width to fit
        (
            "0 0 20 10",
            100,
            100,
            100,
            0,
            Affine2D(a=10, b=0, c=0, d=-10, e=0, f=100),
            200,
        ),
        # taller than wide: uniformly scale by height, center within advance width
        (
            "0 0 10 20",
            100,
            100,
            100,
            0,
            Affine2D(a=5, b=0, c=0, d=-5, e=25, f=100),
            100,
        ),
    ],
)
def test_transform_and_width(
    view_box, upem, width, ascender, descender, expected_transform, expected_width
):
    svg_str = (
        '<svg version="1.1"'
        ' xmlns="http://www.w3.org/2000/svg"'
        f' viewBox="{view_box}"'
        "><defs/></svg>"
    )
    config = FontConfig(
        upem=upem, width=width, ascender=ascender, descender=descender
    ).validate()
    ufo = _ufo(config)
    color_glyph = ColorGlyph.create(
        config, ufo, "duck", 1, [0x0042], SVG.fromstring(svg_str)
    )

    assert color_glyph.transform_for_font_space() == pytest.approx(expected_transform)
    assert ufo[color_glyph.glyph_name].width == expected_width


def _round_coords(paint, prec=5):
    if isinstance(paint, PaintLinearGradient):
        return dataclasses.replace(
            paint,
            p0=Point(round(paint.p0.x, prec), round(paint.p0.y, prec)),
            p1=Point(round(paint.p1.x, prec), round(paint.p1.y, prec)),
            p2=Point(round(paint.p2.x, prec), round(paint.p2.y, prec)),
        )
    if isinstance(paint, PaintRadialGradient):
        return dataclasses.replace(
            paint,
            c0=Point(round(paint.c0.x, prec), round(paint.c0.y, prec)),
            c1=Point(round(paint.c1.x, prec), round(paint.c1.y, prec)),
            r0=round(paint.r0, prec),
            r1=round(paint.r1, prec),
        )
    if is_transform(paint):
        return transformed(paint.gettransform().round(prec), paint.paint)
    return paint


@pytest.mark.parametrize(
    "svg_in, expected_paints",
    [
        # solid
        (
            "rect.svg",
            (
                PaintGlyph(
                    glyph="M2,2 L8,2 L8,4 L2,4 L2,2 Z",
                    paint=PaintSolid(color=Color.fromstring("blue")),
                ),
                PaintGlyph(
                    glyph="M4,4 L10,4 L10,6 L4,6 L4,4 Z",
                    paint=PaintSolid(color=Color.fromstring("blue", alpha=0.8)),
                ),
            ),
        ),
        # linear
        (
            "linear_gradient_rect.svg",
            (
                PaintGlyph(
                    glyph="M2,2 L8,2 L8,4 L2,4 L2,2 Z",
                    paint=PaintLinearGradient(
                        stops=(
                            ColorStop(stopOffset=0.1, color=Color.fromstring("blue")),
                            ColorStop(
                                stopOffset=0.9, color=Color.fromstring("cyan", 0.8)
                            ),
                        ),
                        p0=Point(200, 800),
                        p1=Point(800, 800),
                        p2=Point(200, 600),
                    ),
                ),
            ),
        ),
        # radial on square using objectBoundingBox (no wrapping PaintTransform needed)
        (
            "radial_gradient_square.svg",
            (
                PaintGlyph(
                    glyph="M0,0 L10,0 L10,10 L0,10 L0,0 Z",
                    paint=PaintRadialGradient(
                        extend=Extend.REPEAT,
                        stops=(
                            ColorStop(
                                stopOffset=0.05, color=Color.fromstring("fuchsia")
                            ),
                            ColorStop(
                                stopOffset=0.75, color=Color.fromstring("orange")
                            ),
                        ),
                        c0=Point(500, 500),
                        c1=Point(500, 500),
                        r0=0,
                        r1=500,
                    ),
                ),
            ),
        ),
        # radial on non-square rect using objectBoundingBox
        (
            "radial_gradient_rect.svg",
            (
                PaintGlyph(
                    glyph="M2,2 L8,2 L8,4 L2,4 L2,2 Z",
                    paint=PaintScale(
                        scaleX=1.0,
                        scaleY=0.33333,
                        paint=PaintRadialGradient(
                            extend=Extend.REPEAT,
                            stops=(
                                ColorStop(
                                    stopOffset=0.05, color=Color.fromstring("fuchsia")
                                ),
                                ColorStop(
                                    stopOffset=0.75, color=Color.fromstring("orange")
                                ),
                            ),
                            c0=Point(500, 2100),
                            c1=Point(500, 2100),
                            r0=0,
                            r1=300,
                        ),
                    ),
                ),
            ),
        ),
        # radial with gradientTransform
        (
            "radial_gradient_transform.svg",
            (
                PaintGlyph(
                    glyph="M0,0 L1000,0 L1000,1000 L0,1000 L0,0 Z",
                    paint=PaintTransform(
                        transform=(0.93969, 0.0, -0.34202, 0.93969, 0.0, 0.0),
                        paint=PaintRadialGradient(
                            stops=(
                                ColorStop(
                                    stopOffset=0.0, color=Color.fromstring("darkblue")
                                ),
                                ColorStop(
                                    stopOffset=0.5, color=Color.fromstring("skyblue")
                                ),
                                ColorStop(
                                    stopOffset=1.0, color=Color.fromstring("darkblue")
                                ),
                            ),
                            c0=Point(x=733.1865, y=532.08885),
                            c1=Point(x=733.1865, y=532.08885),
                            r0=0,
                            r1=532.08885,
                        ),
                    ),
                ),
            ),
        ),
        # linear with gradientTransform
        (
            "linear_gradient_transform.svg",
            (
                PaintGlyph(
                    glyph="M0,0 L1000,0 L1000,1000 L0,1000 L0,0 Z",
                    paint=PaintLinearGradient(
                        extend=Extend.REFLECT,
                        stops=(
                            ColorStop(stopOffset=0.0, color=Color.fromstring("green")),
                            ColorStop(stopOffset=0.5, color=Color.fromstring("white")),
                            ColorStop(stopOffset=1.0, color=Color.fromstring("red")),
                        ),
                        p0=Point(x=0, y=1000),
                        p1=Point(x=1000, y=1000),
                        p2=Point(x=-1000, y=0),
                    ),
                ),
            ),
        ),
        # linear with both gradientTransform and objectBoundingBox
        (
            "linear_gradient_transform_2.svg",
            (
                PaintGlyph(
                    glyph="M100,450 L900,450 L900,550 L100,550 L100,450 Z",
                    paint=PaintLinearGradient(
                        stops=(
                            ColorStop(stopOffset=0.05, color=Color.fromstring("gold")),
                            ColorStop(stopOffset=0.95, color=Color.fromstring("red")),
                        ),
                        p0=Point(x=100, y=550),
                        p1=Point(x=900, y=550),
                        p2=Point(x=100, y=450),
                    ),
                ),
                PaintGlyph(
                    glyph="M450,100 L550,100 L550,900 L450,900 L450,100 Z",
                    paint=PaintLinearGradient(
                        stops=(
                            ColorStop(stopOffset=0.05, color=Color.fromstring("gold")),
                            ColorStop(stopOffset=0.95, color=Color.fromstring("red")),
                        ),
                        p0=Point(x=450, y=900),
                        p1=Point(x=450, y=100),
                        p2=Point(x=350, y=900),
                    ),
                ),
            ),
        ),
        # radial with gradientTransform with almost zero scale, non-zero skew
        (
            "radial_gradient_transform_2.svg",
            (
                PaintGlyph(
                    glyph=(
                        "M51.56,22.14 C51.56,16.32 47.74,6.55 36.02,6.55 C23.9,6.55 20.18,17.89"
                        " 20.18,22.14 C20.18,34.96 21.33,41.31 22.6,43.93 C22.84,44.43 23.56,44.66"
                        " 23.79,43.46 C23.79,43.46 22.89,35.69 22.79,30.15 C22.77,28.86 22.37,24.06"
                        " 25.08,23.46 C35,21.23 40.61,15.97 40.61,15.97 C42.07,19.16 46.63,22.26"
                        " 48.27,23.45 C49.62,24.42 49.43,28.42 49.4,30.12 L48.05,43.44 C48.05,43.44"
                        " 48.13,46.61 49.44,43.94 C50.75,41.26 51.56,26.44 51.56,22.14 Z"
                    ),
                    paint=PaintTransform(
                        transform=(0.0, -1.0, 0.9288, 0.0, 0.0, 0.0),
                        paint=PaintRadialGradient(
                            stops=(
                                ColorStop(
                                    stopOffset=0.0, color=Color.fromstring("white")
                                ),
                                ColorStop(
                                    stopOffset=1.0, color=Color.fromstring("black")
                                ),
                            ),
                            c0=Point(x=-973.125, y=301.77018),
                            c1=Point(x=-973.125, y=301.77018),
                            r0=0.0,
                            r1=129.01562,
                        ),
                    ),
                ),
            ),
        ),
        # Shape with opacity, should apply to gradient colors
        # See https://github.com/googlefonts/picosvg/issues/76
        (
            "gradient_opacity.svg",
            (
                PaintGlyph(
                    glyph="M2,2 L8,2 L8,4 L2,4 L2,2 Z",
                    paint=PaintLinearGradient(
                        stops=(
                            ColorStop(
                                stopOffset=0.1,
                                color=Color.fromstring("blue", alpha=0.4),
                            ),
                            ColorStop(
                                stopOffset=0.9,
                                color=Color.fromstring("cyan", alpha=0.4 * 0.8),
                            ),
                        ),
                        p0=Point(200.0, 800.0),
                        p1=Point(800.0, 800.0),
                        p2=Point(200.0, 600.0),
                    ),
                ),
                PaintGlyph(
                    glyph="M2,5 L8,5 L8,7 L2,7 L2,5 Z",
                    paint=PaintScale(
                        scaleX=1.0,
                        scaleY=0.33333,
                        paint=PaintRadialGradient(
                            stops=(
                                ColorStop(
                                    stopOffset=0.1,
                                    color=Color.fromstring("red", alpha=0.5),
                                ),
                                ColorStop(
                                    stopOffset=0.9,
                                    color=Color.fromstring("yellow", alpha=0.5 * 0.8),
                                ),
                            ),
                            c0=Point(x=500.0, y=1200.0),
                            c1=Point(x=500.0, y=1200.0),
                            r0=0.0,
                            r1=300.0,
                        ),
                    ),
                ),
            ),
        ),
        (
            # viewBox="0 0 10 8" (w > h), with a linearGradient from (1, 1) to (9, 1).
            # The default advance width gets scaled by aspect ratio 1000 * 10/8 == 1250.
            # Test that linearGradient p0 and p1 are centered horizontally relative to
            # the scaled advance width (and not relative to the default advance width).
            "gradient_non_square_viewbox.svg",
            (
                PaintGlyph(
                    glyph="M1,1 L9,1 L9,7 L1,7 L1,1 Z",
                    paint=PaintLinearGradient(
                        stops=(
                            ColorStop(stopOffset=0.1, color=Color.fromstring("blue")),
                            ColorStop(stopOffset=0.9, color=Color.fromstring("cyan")),
                        ),
                        p0=Point(125.0, 875.0),
                        p1=Point(1125.0, 875.0),
                        p2=Point(125.0, 125.0),
                    ),
                ),
            ),
        ),
        # Gradient with opacity resolves to composition of a solid color with alpha
        # and the layer(s) in question
        (
            "group_opacity.svg",
            (
                PaintGlyph(
                    glyph="M19,11 L61,11 L61,121 L19,121 Z M29,21 L29,111 L51,111 L51,21 Z",
                    paint=PaintSolid(color=Color(red=0, green=0, blue=0, alpha=0.8)),
                ),
                PaintComposite(
                    mode=CompositeMode.SRC_IN,
                    source=PaintColrLayers(
                        layers=(
                            PaintGlyph(
                                glyph="M10,30 L100,30 L100,120 L10,120 L10,30 Z",
                                paint=PaintSolid(
                                    color=Color(red=255, green=0, blue=0, alpha=1.0)
                                ),
                            ),
                            PaintGlyph(
                                glyph="M5,25 L105,25 L105,125 L5,125 Z M15,35 L15,115 L95,115 L95,35 Z",
                                paint=PaintSolid(
                                    color=Color(red=0, green=0, blue=255, alpha=1.0)
                                ),
                            ),
                        ),
                    ),
                    backdrop=PaintSolid(color=Color(red=0, green=0, blue=0, alpha=0.6)),
                ),
                PaintGlyph(
                    glyph=(
                        "M105,50 Q105,67.475 100.288,80.04 Q94.678,95 85,95 Q75.322,95 69.712,80.04 Q65,67.475"
                        " 65,50 Q65,32.525 69.712,19.96 Q75.322,5 85,5 Q94.678,5 100.288,19.96 Q105,32.525"
                        " 105,50 Z M95,50 Q95,34.338 90.925,23.471 Q87.748,15 85,15 Q82.252,15 79.075,23.471"
                        " Q75,34.338 75,50 Q75,65.662 79.075,76.529 Q82.252,85 85,85 Q87.748,85 90.925,76.529"
                        " Q95,65.662 95,50 Z"
                    ),
                    paint=PaintSolid(color=Color(red=0, green=0, blue=0, alpha=1.0)),
                ),
            ),
        ),
    ],
)
def test_color_glyph_layers(svg_in, expected_paints):
    config = FontConfig(upem=1000, ascender=1000, descender=0, width=1000)
    color_glyph = ColorGlyph.create(
        config, _ufo(config), "duck", 1, [0x0042], _nsvg(svg_in)
    ).mutating_traverse(_round_coords)

    actual_paints = color_glyph.painted_layers
    if actual_paints != expected_paints:
        print("A:")
        print(_pprint(actual_paints))
        print("E:")
        print(_pprint(expected_paints))
    assert actual_paints == expected_paints


# TODO test that a composite is NOT formed where paint changes
