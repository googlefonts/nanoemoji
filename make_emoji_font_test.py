import difflib
import io
import os
import sys
import make_emoji_font
from nanosvg.svg import SVG
import pytest


def _nsvg(filename):
    return SVG.parse(filename).tonanosvg()


def _color_font_config(color_format, svg_in, output_format):
    return make_emoji_font.ColorFontConfig(
        upem=100,
        family='UnitTest',
        color_format=color_format,
        output_format=output_format), [(svg_in, (0xE000,), _nsvg(svg_in))]


def _normalize_ttx(ttx):
    lines = []
    for line in ttx.splitlines():
        # Elide ttFont attributes because ttLibVersion may change,
        # and use os-native line separators so we can run difflib.
        if line.startswith("<ttFont "):
            lines.append("<ttFont>" + os.linesep)
        else:
            lines.append(line + os.linesep)
    return lines


def _check_ttx(svg_in, ttfont, expected_ttx):
    actual_ttx = io.StringIO()
    # Timestamps inside files #@$@#%@#
    ttfont.saveXML(actual_ttx, skipTables=['head', 'hhea', 'maxp', 'name', 'post', 'OS/2'])
    actual = _normalize_ttx(actual_ttx.getvalue())

    with open(expected_ttx) as f:
        expected = _normalize_ttx(f.read())
    if actual != expected:
        for line in difflib.unified_diff(
            expected,
            actual,
            fromfile=f'{expected_ttx} (expected)',
            tofile=f'{expected_ttx} (actual)',
        ):
            sys.stderr.write(line)
        pytest.fail(f'TTX for font from {svg_in} is wrong')


@pytest.mark.parametrize(
    "filename, codepoints",
    [
        # Noto Emoji, single codepoint
        ('emoji_u1f378.svg', (0x1f378,)),
        # Noto Emoji, multiple codepoints
        ('emoji_u1f385_1f3fb.svg', (0x1f385, 0x1f3fb)),
        # Noto Emoji, lots of codepoints!
        (
            'emoji_u1f469_1f3fd_200d_1f91d_200d_1f468_1f3ff.svg',
            (0x1f469, 0x1f3fd, 0x200d, 0x1f91d, 0x200d, 0x1f468, 0x1f3ff)
        ),
        # Twemoji, single codepoint
        ('2198.svg', (0x2198,)),
        # Twemoji, multiple codepoints
        ('1f9d1-200d-1f91d-200d-1f9d1.svg', (0x1f9d1, 0x200d, 0x1f91d, 0x200d, 0x1f9d1)),
    ]
)
def test_codepoints_from_filename(filename, codepoints):
    assert codepoints == make_emoji_font._codepoints_from_filename(filename)


# TODO test that width, height are removed from svg
# TODO test that enable-background is removed from svg
# TODO test that id=glyph# is added to svg
# TODO test svg compressed false, svgz true

# TODO test round-trip svg => colrv1 => svg


@pytest.mark.parametrize(
    "svg_in, expected_ttx, color_format, output_format",
    [
        # simple fill on rect
        ('rect.svg', 'rect_colr_0.ttx', 'colr_0', '.ttf'),
        ('rect.svg', 'rect_colr_1.ttx', 'colr_1', '.ttf'),

        # linear gradient on rect
        ('linear_gradient_rect.svg', 'linear_gradient_rect.ttx', 'colr_1', '.ttf'),
    ]
)
def test_make_emoji_font(svg_in, expected_ttx, color_format, output_format):
    config, glyph_inputs = _color_font_config(color_format, svg_in, output_format)
    _, ttfont = make_emoji_font._generate_color_font(config, glyph_inputs)
    _check_ttx(svg_in, ttfont, expected_ttx)
