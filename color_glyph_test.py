from colors import Color
from color_glyph import ColorGlyph
from fontTools.misc.transform import Transform
from nanosvg.svg import SVG
import os
from paint import *
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
        ("0 0 1024 1024", 1024, Transform(1, 0, 0, -1, 0, 1024)),
        # noto emoji norm. scale, flip y
        ("0 0 128 128", 1024, Transform(8, 0, 0, -8, 0, 1024)),
        # noto emoji emoji_u26be.svg viewBox. Translate, scale, flip y
        ("-151 297 128 128", 1024, Transform(3.67, 0, 0, -6.059, 151, 1024 - 297)),
        # made up example. Translate, scale, flip y
        ("10 11 20 21", 100, Transform(10, 0, 0, -10, -10, 100 - 11)),
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

    assert color_glyph.transform_for_font_space() == expected_transform


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
                    )
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
                )
            },
        ),
        # TODO gradientTransform => affine2x2
    ],
)
def test_paint_from_shape(svg_in, expected_paints):
    color_glyph = ColorGlyph.create(_ufo(256), "duck", 1, [0x0042], _nsvg(svg_in))
    assert color_glyph.paints() == expected_paints
