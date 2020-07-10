#!/usr/bin/env python3
"""Convert COLRv1 font to a set of SVG files, one per base color glyph."""
import os
import sys

# extend PYTHONPATH to include ../tests dir where colr_to_svg module is located
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), "tests"))

from colr_to_svg import colr_to_svg
from fontTools.ttLib import TTFont
from picosvg.geometric_types import Rect
from lxml import etree


VIEW_BOX_SIZE = 128

try:
    fontfile, destdir = sys.argv[1:]
except ValueError:
    sys.exit("usage: ./colr2svg.py FONTFILE SVG_OUTPUT_DIR")

font = TTFont(fontfile)
viewbox = Rect(0, 0, VIEW_BOX_SIZE, VIEW_BOX_SIZE)

os.makedirs(destdir, exist_ok=True)

for glyph_name, svg in colr_to_svg(viewbox, font).items():
    output_file = os.path.join(destdir, f"{glyph_name}.svg")
    with open(output_file, "wb") as f:
        f.write(etree.tostring(svg.svg_root, pretty_print=True))
    print(f"{output_file}")
