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

## How to cut a new release

Use `git tag -a` to make a new annotated tag, or `git tag -s` for a GPG-signed annotated tag,
if you prefer.

Name the new tag with with a leading 'v' followed by three MAJOR.MINOR.PATCH digits, like in
[semantic versioning](https://semver.org/). Look at the existing tags for examples.

In the tag message write some short release notes describing the changes since the previous
tag.

Finally, push the tag to the remote repository (e.g. assuming upstream is called `origin`):

```
$ git push origin v0.4.3
```

This will trigger the CI to build the distribution packages and upload them to the
[Python Package Index](https://pypi.org/project/nanoemoji/) automatically, if all the tests
pass successfully.
