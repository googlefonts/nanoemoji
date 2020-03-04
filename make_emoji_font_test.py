import make_emoji_font as mef
import pytest

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
    assert codepoints == mef._codepoints_from_filename(filename)


# TODO test that width, height are removed from svg
# TODO test that enable-background is removed from svg
# TODO test that id=glyph# is added to svg