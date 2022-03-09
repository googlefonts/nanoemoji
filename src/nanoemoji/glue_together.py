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

"""Copies color assets from one font to another.

Both must use the same glyph names."""
from absl import app
from absl import flags
from absl import logging
from fontTools.ttLib.tables import otTables as ot
from fontTools import ttLib
from nanoemoji.colr import paints_of_type
import os
from typing import Iterable, Tuple


FLAGS = flags.FLAGS


flags.DEFINE_string("target_font", None, "Font assets are copied into.")
flags.DEFINE_string("donor_font", None, "Font from which assets are copied.")
flags.DEFINE_string("color_table", None, "The color table to copy.")
flags.DEFINE_string("output_file", None, "Font assets are copied into.")


def _copy_colr(target: ttLib.TTFont, donor: ttLib.TTFont):
    # Copy all glyphs used by COLR over
    _glyphs_to_copy = {
        p.Glyph for p in paints_of_type(donor, ot.PaintFormat.PaintGlyph)
    }

    for glyph_name in _glyphs_to_copy:
        target["glyf"][glyph_name] = donor["glyf"][glyph_name]

        if glyph_name in target["hmtx"].metrics:
            assert (
                target["hmtx"][glyph_name] == donor["hmtx"][glyph_name]
            ), f"Unexpected change in metrics for {glyph_name}"
        else:
            # new glyph, new metrics
            target["hmtx"][glyph_name] = donor["hmtx"][glyph_name]

    target["CPAL"] = donor["CPAL"]
    target["COLR"] = donor["COLR"]


def _svg_glyphs(font: ttLib.TTFont) -> Iterable[Tuple[int, str]]:
    for _, min_gid, max_gid in font["SVG "].docList:
        for gid in range(min_gid, max_gid + 1):
            yield gid, font.getGlyphName(gid)


def _copy_svg(target: ttLib.TTFont, donor: ttLib.TTFont):
    # SVG is exciting because nanoemoji likes to restructure glyph order
    # To keep things simple, let's build a new glyph order that keeps all the svg font gids stable
    target_glyph_order = list(target.getGlyphOrder())
    svg_glyphs = {gn for _, gn in _svg_glyphs(donor)}
    non_svg_target_glyphs = [gn for gn in target_glyph_order if gn not in svg_glyphs]
    new_glyph_order = []

    for svg_gid, svg_glyph_name in _svg_glyphs(donor):
        # we want gid to remain stable so copy non-svg glyphs until that will be true
        while len(new_glyph_order) < svg_gid:
            new_glyph_order.append(non_svg_target_glyphs.pop(0))
        new_glyph_order.append(svg_glyph_name)

    new_glyph_order.extend(non_svg_target_glyphs)  # any leftovers?

    target.setGlyphOrder(new_glyph_order)
    target["SVG "] = donor["SVG "]


def main(argv):
    target = ttLib.TTFont(FLAGS.target_font)
    donor = ttLib.TTFont(FLAGS.donor_font)

    # TODO lookup, guess fn name, etc
    if FLAGS.color_table == "COLR":
        _copy_colr(target, donor)
    elif FLAGS.color_table == "SVG":
        _copy_svg(target, donor)
    else:
        # TODO: SVG support
        # Note that nanoemoji svg reorders glyphs to pack svgs nicely
        # The merged font may need to update to the donors glyph order for this to work
        raise ValueError(f"Unsupported color table '{FLAGS.color_table}'")

    target.save(FLAGS.output_file)
    logging.info("Wrote %s", FLAGS.output_file)


if __name__ == "__main__":
    flags.mark_flag_as_required("target_font")
    flags.mark_flag_as_required("donor_font")
    flags.mark_flag_as_required("color_table")
    flags.mark_flag_as_required("output_file")
    app.run(main)
