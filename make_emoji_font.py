"""Create an emoji font from a set of SVGs.

Sample usage:
make_emoji_font.py -v 1 $(find ~/oss/noto-emoji/svg -name '*.svg' | head -10)
"""
from absl import app
from absl import flags
from absl import logging
from nanosvg.svg import SVG
import sys

FLAGS = flags.FLAGS

def _nanosvgs(filenames):
    for svg_file in filenames:
        logging.debug(f'Processing {svg_file}')
        try:
            yield svg_file, SVG.parse(svg_file).tonanosvg()
        except Exception as e:
            logging.warning(f'{svg_file} failed: {e}')


def main(argv):
    num_success = 0
    for svg_file, nanosvg in _nanosvgs(argv[1:]):
        num_success += 1
    print(f'{num_success}/{len(argv[1:])} parsed successfully')


if __name__ == "__main__":
    app.run(main)