from nanoemoji.png import PNG
import pytest


def test_good_png_signature():
    # example from https://en.wikipedia.org/wiki/Portable_Network_Graphics
    data = bytes(
        int(b, 16)
        for b in (
            "89 50 4E 47 0D 0A 1A 0A 00 00 00 0D 49 48 44 52 "
            "00 00 00 01 00 00 00 01 08 02 00 00 00 90 77 53 "
            "DE 00 00 00 0C 49 44 41 54 08 D7 63 F8 CF C0 00 "
            "00 03 01 01 00 18 DD 8D B0 00 00 00 00 49 45 4E "
            "44 AE 42 60 82"
        ).split()
    )
    assert PNG(data) == data


def test_bad_png_signature():
    with pytest.raises(ValueError, match="bad signature"):
        PNG(b"<?xml")
