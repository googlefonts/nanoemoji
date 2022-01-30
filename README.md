[![CI Build Status](https://github.com/googlefonts/nanoemoji/workflows/Continuous%20Test%20+%20Deploy/badge.svg?branch=main)](https://github.com/googlefonts/nanoemoji/actions/workflows/ci.yml?query=workflow%3ATest+branch%3Amain)
[![PyPI](https://img.shields.io/pypi/v/nanoemoji.svg)](https://pypi.org/project/nanoemoji/)
[![pyup](https://pyup.io/repos/github/googlefonts/nanoemoji/shield.svg)](https://pyup.io/repos/github/googlefonts/nanoemoji)


# nanoemoji
A wee tool to build color fonts, including the proposed [COLRv1](https://github.com/googlefonts/colr-gradients-spec/blob/main/colr-gradients-spec.md). Relies heavily on Skia via [picosvg](https://github.com/googlefonts/picosvg).

For example, to build a COLRv1 font with a focus on [handwriting](https://rsheeter.github.io/android_fonts/emoji.html?q=u:270d) do the following in a [venv](https://docs.python.org/3/library/venv.html):

```bash
pip install -e .
nanoemoji --helpfull
nanoemoji --color_format glyf_colr_1 $(find ../noto-emoji/svg -name 'emoji_u270d*.svg')
```

Requires Python 3.7 or greater.

## Color table support

| Format | Support | Notes |
| --- | --- | --- |
| [COLRv1](https://docs.microsoft.com/en-us/typography/opentype/spec/colr#colr-formats) | Yes | x-glyph reuse |
| [COLRv0](https://docs.microsoft.com/en-us/typography/opentype/spec/colr#colr-formats) | Yes | x-glyph reuse (limited), no gradients |
| [SVG](https://docs.microsoft.com/en-us/typography/opentype/spec/svg) | Yes | x-glyph reuse |
| [sbix](https://docs.microsoft.com/en-us/typography/opentype/spec/sbix) | Yes* | Only for Mac Safari due to https://github.com/harfbuzz/harfbuzz/issues/2679#issuecomment-1021419864. Only square bitmaps. Requires [`resvg`](https://github.com/RazrFalcon/resvg).|
| [CBDT](https://docs.microsoft.com/en-us/typography/opentype/spec/cbdt) | Yes* |  Only square bitmaps. Requires [`resvg`](https://github.com/RazrFalcon/resvg).|

\* to use bitmap formats (sbix, CBDT) you must `cargo install resvg` or otherwise insure `resvg` is on PATH.

## Releasing

See https://googlefonts.github.io/python#make-a-release.

## QA

To help confirm valid output `nanoemoji` can optionally perform image diffs
between browser rendering of the original SVGs and rendering from the compiled font.

Chrome must be installed in the normal location.

Usage:

```
# Get some svgs to play with
git clone --recursive git@github.com:googlefonts/color-fonts.git

# Now run nanoemoji, render some hands, and see how we do!
# https://rsheeter.github.io/android_fonts/emoji.html?q=u:270b
nanoemoji --gen_svg_font_diffs \
	$(find color-fonts/font-srcs/noto-emoji/svg -name 'emoji_u270b*.svg')

```
