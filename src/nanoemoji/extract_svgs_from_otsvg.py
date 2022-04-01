# Copyright 2022 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Generate SVG files from the SVG font table."""
from absl import app
from absl import flags
from absl import logging
from fontTools import ttLib
from lxml import etree
from nanoemoji import codepoints
from nanoemoji.color_glyph import map_viewbox_to_otsvg_space
from nanoemoji.extract_svgs import svg_glyphs
from nanoemoji import util
import os
import shutil
import subprocess
import sys
from pathlib import Path
from picosvg.svg import SVG
from picosvg.svg_meta import strip_ns


FLAGS = flags.FLAGS


flags.DEFINE_string("output_dir", None, "Output dir. Files written to <glyph id>.svg.")
flags.DEFINE_string(
    "log_level",
    "INFO",
    "The threshold for what messages will be logged. One of DEBUG, INFO, WARN, "
    "ERROR, or FATAL.",
)


def main(argv):
    logging.set_verbosity(FLAGS.log_level)

    font_file = util.only(argv, lambda a: a.endswith(".ttf"))
    out_dir = Path(FLAGS.output_dir)
    assert out_dir.is_dir(), f"{FLAGS.output_dir} is not a directory"

    font = ttLib.TTFont(font_file)
    assert "SVG " in font, f"No SVG table in {font_file}"
    upem = font["head"].unitsPerEm
    ascender = font["OS/2"].sTypoAscender
    descender = font["OS/2"].sTypoDescender
    metrics = font["hmtx"].metrics
    logging.debug("Writing svgs from %s to %s", font_file, out_dir)
    logging.debug("upem %d ascender %d descender %d", upem, ascender, descender)

    # We want a subsequent nanoemoji scale to be 1:1
    # So use the font height (global) and width (per glyph) as the svg viewbox
    height = ascender - descender

    for gid, svg in svg_glyphs(font):
        svg_defs = etree.Element("defs")
        svg_g = etree.Element("g")
        svg_g.attrib["transform"] = f"translate(0, {ascender})"

        for el in svg.svg_root:
            if strip_ns(el.tag) == "defs":
                svg_defs.append(el)
            else:
                svg_g.append(el)

        svg.svg_root.append(svg_defs)
        svg.svg_root.append(svg_g)

        glyph_name = font.getGlyphName(gid)
        width, _ = metrics[glyph_name]
        svg.svg_root.attrib["viewBox"] = f"0 0 {width} {height}"
        dest_file = out_dir / f"{gid:05d}.svg"
        with open(dest_file, "w") as f:
            f.write(svg.tostring(pretty_print=True))
        logging.debug("Wrote %s", dest_file)


if __name__ == "__main__":
    flags.mark_flag_as_required("output_dir")
    app.run(main)
