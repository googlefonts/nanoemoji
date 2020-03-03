from color_glyph import ColorGlyph
from fontTools.misc.transform import Transform
from nanosvg.svg import SVG
import pytest
import ufoLib2

# TODO test _glyph_name obeys codepoint order


def _ufo(upem):
    ufo = ufoLib2.Font()
    ufo.info.unitsPerEm = upem
    return ufo


def _test_file(filename):
    return os.path.join(os.path.dirname(__file__), filename)


@pytest.mark.parametrize(
    "view_box, upem, expected_transform",
    [
        # same upem, flip y
        ("0 0 1024 1024", 1024, Transform(1, 0, 0, -1, 0, 0)),

        # noto emoji norm. scale, flip y
        ("0 0 128 128", 1024, Transform(8, 0, 0, -8, 0, 0)),

        # noto emoji emoji_u26be.svg viewBox. Translate, scale, flip y
        ("-151 297 128 128", 1024, Transform(3.67, 0, 0, -6.059, 151, -297)),

        # made up example. Translate, scale, flip y
        ("10 11 20 21", 100, Transform(10, 0, 0, -10, -10, -11)),
    ],
)
def test_transform(view_box, upem, expected_transform):
    svg_str = ('<svg version="1.1"'
               ' xmlns="http://www.w3.org/2000/svg"'
               f' viewBox="{view_box}"'
               '/>')
    color_glyph = ColorGlyph.create(_ufo(upem),
                                    'duck',
                                    [0x0042],
                                    SVG.fromstring(svg_str))

    assert color_glyph.transform_for_font_space() == expected_transform