[![CI Build Status](https://github.com/googlefonts/nanoemoji/workflows/Continuous%20Test%20+%20Deploy/badge.svg?branch=main)](https://github.com/googlefonts/nanoemoji/actions/workflows/ci.yml?query=workflow%3ATest+branch%3Amain)
[![PyPI](https://img.shields.io/pypi/v/nanoemoji.svg)](https://pypi.org/project/nanoemoji/)
[![pyup](https://pyup.io/repos/github/googlefonts/nanoemoji/shield.svg)](https://pyup.io/repos/github/googlefonts/nanoemoji)


# nanoemoji
A wee tool to build color fonts, including the proposed [COLRv1](https://github.com/googlefonts/colr-gradients-spec/blob/main/colr-gradients-spec.md). Relies heavily on Skia via [picosvg](https://github.com/googlefonts/picosvg), as well as [`resvg`](https://github.com/RazrFalcon/resvg) to rasterize SVG to PNG for the bitmap color formats.

For example, to build a COLRv1 font with a focus on [handwriting](https://rsheeter.github.io/android_fonts/emoji.html?q=u:270d) do the following in a [venv](https://docs.python.org/3/library/venv.html):

```bash
pip install -e .
nanoemoji --helpfull
nanoemoji --color_format glyf_colr_1 $(find ../noto-emoji/svg -name 'emoji_u270d*.svg')
```

Requires Python 3.8 or greater.

## Color table support

| Format | Support | Notes |
| --- | --- | --- |
| [COLRv1](https://docs.microsoft.com/en-us/typography/opentype/spec/colr#colr-formats) | Yes | x-glyph reuse |
| [COLRv0](https://docs.microsoft.com/en-us/typography/opentype/spec/colr#colr-formats) | Yes | x-glyph reuse (limited), no gradients |
| [SVG](https://docs.microsoft.com/en-us/typography/opentype/spec/svg) | Yes | x-glyph reuse |
| [sbix](https://docs.microsoft.com/en-us/typography/opentype/spec/sbix) | Yes | Only for Mac Safari due to https://github.com/harfbuzz/harfbuzz/issues/2679#issuecomment-1021419864. Only square bitmaps. Uses [`resvg`](https://github.com/RazrFalcon/resvg).|
| [CBDT](https://docs.microsoft.com/en-us/typography/opentype/spec/cbdt) | Yes |  Only square bitmaps. Uses [`resvg`](https://github.com/RazrFalcon/resvg).|

### Adding color tables to existing fonts

:warning: _under active development, doubtless full of bugs_

Given at least one vector color table (COLR or SVG) the other vector color table and bitmap table(s)
can be generated:

```shell
# Adds COLR to a font with SVG and vice versa
maximum_color my_colr_font.ttf

# Adds COLR to a font with SVG and vice versa, and generates a CBDT table
maximum_color --bitmaps my_colr_font.ttf
```

The intended result is a font that will Just Work in any modern browser:

| Color table | Target browser | Notes |
| --- | --- | --- |
| COLR | Chrome 98+ | https://developer.chrome.com/blog/colrv1-fonts/ |
| SVG | Firefox, Safari | |
| CBDT | Chrome <98 | Only generated if you pass `--bitmaps` to `maximum_color`|

Note that at time of writing Chrome 98+ prefers CBDT to COLR. Same for any environment,
such as Android, that relies on Skia, which in turns depends on FreeType to parse color
tables (cf. [Skia's issue 12945][skia-12945] and [FreeType's issue 1142][ft-1142]).
Also CBDT is huge. So ... maybe take the resulting font and subset it per-browser if at
all possible. Wouldn't it be nice if Google Fonts did that for you?

[skia-12945]: https://bugs.chromium.org/p/skia/issues/detail?id=12945
[ft-1142]: https://gitlab.freedesktop.org/freetype/freetype/-/issues/1142

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
