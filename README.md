[![Travis Build Status](https://travis-ci.org/googlefonts/nanoemoji.svg?branch=master)](https://travis-ci.org/googlefonts/nanoemoji)
[![PyPI](https://img.shields.io/pypi/v/nanoemoji.svg)](https://pypi.org/project/nanoemoji/)
[![pyup](https://pyup.io/repos/github/googlefonts/nanoemoji/shield.svg)](https://pyup.io/repos/github/googlefonts/nanoemoji)


# nanoemoji
A wee tool to build color fonts, including the proposed [COLRv1](https://github.com/googlefonts/colr-gradients-spec/blob/master/colr-gradients-spec.md). Relies heavily on Skia via [picosvg](https://github.com/googlefonts/picosvg).

For example, to build a COLRv1 font with a focus on [handwriting](https://rsheeter.github.io/android_fonts/emoji.html?q=u:270d) do the following in a [venv](https://docs.python.org/3/library/venv.html):

```bash
pip install -e .
nanoemoji --helpfull
nanoemoji --color_format glyf_colr_1 $(find ../noto-emoji/svg -name 'emoji_u270d*.svg')
```

## Releasing

See https://googlefonts.github.io/python#make-a-release.
