[![Travis Build Status](https://travis-ci.org/rsheeter/nanoemoji.svg)](https://travis-ci.org/rsheeter/nanoemoji)
# nanoemoji
A wee tool to build color fonts.

For example, to build a COLRv1 font with a focus on [handwriting](https://rsheeter.github.io/android_fonts/emoji.html?q=u:270d) do the following in a [venv](https://docs.python.org/3/library/venv.html):

```bash
pip install -e .
nanoemoji --helpfull
nanoemoji --color_format colr_1 $(find ../noto-emoji/svg -name 'emoji_u270d*.svg')
```
