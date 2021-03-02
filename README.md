[![CI Build Status](https://github.com/googlefonts/nanoemoji/workflows/Continuous%20Test%20+%20Deploy/badge.svg)](https://github.com/googlefonts/nanoemoji/actions/workflows/ci.yml?query=workflow%3ATest)
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

## Releasing

See https://googlefonts.github.io/python#make-a-release.

## QA

To help confirm valid output `nanoemoji` can optionally perform image diffs
between resvg rendering of the original SVGs and Skia rendering from the compiled font. Usage:

```
# Make sure colr_test is compiled and on PATH
git clone git@github.com:rsheeter/skia_colr.git
(cd colr_test && ./build_colr.sh)
export PATH="$PATH:$(cd skia_colr/out/Static/ && pwd)"
which colr_test

# Make sure resvg tool is compiled and on PATH. E.g. you can use cargo to install it
cargo install resvg
which resvg

# Get some svgs to play with
git clone --recursive git@github.com:googlefonts/color-fonts.git

# Now run nanoemoji, render some hands, and see how we do!
# https://rsheeter.github.io/android_fonts/emoji.html?q=u:270b
nanoemoji --gen_svg_font_diffs \
	$(find color-fonts/font-srcs/noto-emoji/svg -name 'emoji_u270b*.svg')

```
