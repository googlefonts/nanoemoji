"""Create an emoji font from a set of SVGs.

UFO handling informed by Cosimo's
https://gist.github.com/anthrotype/2acbc67c75d6fa5833789ec01366a517

Sample usage:
make_emoji_font.py -v 1 $(find ~/oss/noto-emoji/svg -name '*.svg')
make_emoji_font.py $(find ~/oss/twemoji/assets/svg -name '*.svg')
"""
from absl import app
from absl import flags
from absl import logging
from fontTools.misc.transform import Transform
from nanosvg.svg import SVG
import os
import regex
import sys

FLAGS = flags.FLAGS

# TODO move to config file?
flags.DEFINE_integer('upem', 1024, 'Units per em.')

def _codepoints_from_filename(filename):
    match = regex.search(r'(?:[-_]?([0-9a-fA-F]{4,}))+', filename)
    if match:
        return tuple(int(s, 16) for s in match.captures(1))
    logging.warning(f'Bad filename {filename}; unable to extract codepoints')
    return None

def _nanosvg(filename):
    try:
        return SVG.parse(filename).tonanosvg()
    except Exception as e:
        logging.warning(f'{filename} failed: {e}')
    return None


def _transform(filename, upem, nsvg):
    vbox = nsvg.view_box()
    if vbox is None:
        logging.warning(f'{filename} has no vbox; no transform will be applied')
        return Transform()
    if vbox[0:2] != (0, 0):
        raise ValueError('viewBox must start at 0,0')
    x_scale = upem / vbox[2]
    y_scale = upem / vbox[3]
    transform = Transform(x_scale, 0, 0, -y_scale, 0, upem)
    logging.debug(f'%s %s', os.path.basename(filename), transform)
    return transform


def _inputs(filenames):
    for filename in filenames:
        codepoints = _codepoints_from_filename(filename)
        nanosvg = _nanosvg(filename)
        if codepoints and nanosvg:
            yield (filename, codepoints, nanosvg)


def main(argv):
    inputs = list(_inputs(argv[1:]))
    logging.info(f'{len(inputs)}/{len(argv[1:])} inputs prepared successfully')

    for filename, codepoints, nsvg in inputs:
        _transform(filename, FLAGS.upem, nsvg)
    # TODO actually build a font

if __name__ == "__main__":
    app.run(main)