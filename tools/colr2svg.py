#!/usr/bin/env python3
"""Convert COLRv1 font to a set of SVG files, one per base color glyph."""
import os
import sys
import argparse

# extend PYTHONPATH to include ../tests dir where colr_to_svg module is located
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), "tests"))

from colr_to_svg import colr_to_svg
from fontTools.ttLib import TTFont
from picosvg.geometric_types import Rect


ROUNDING_NDIGITS = 3
VIEW_BOX_SIZE = 128

parser = argparse.ArgumentParser()
parser.add_argument("fontfile")
parser.add_argument("destdir")
parser.add_argument(
    "--round",
    dest="rounding_ndigits",
    metavar="NDIGITS",
    type=int,
    default=ROUNDING_NDIGITS,
    help="default: %(default)s",
)
parser.add_argument(
    "--viewbox-size",
    metavar="SIZE",
    type=int,
    default=VIEW_BOX_SIZE,
    help="default: %(default)s",
)

options = parser.parse_args(sys.argv[1:])

font = TTFont(options.fontfile)
viewbox = Rect(0, 0, options.viewbox_size, options.viewbox_size)

os.makedirs(options.destdir, exist_ok=True)

for glyph_name, svg in colr_to_svg(
    viewbox, font, rounding_ndigits=options.rounding_ndigits
).items():
    output_file = os.path.join(options.destdir, f"{glyph_name}.svg")
    with open(output_file, "w") as f:
        f.write(svg.tostring(pretty_print=True))
    print(f"{output_file}")
