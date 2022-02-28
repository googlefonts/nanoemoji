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
import os


FLAGS = flags.FLAGS


flags.DEFINE_string("target_font", None, "Font assets are copied into.")
flags.DEFINE_string("donor_font", None, "Font from which assets are copied.")
flags.DEFINE_string("color_table", None, "The color table to copy.")
flags.DEFINE_string("output_file", None, "Font assets are copied into.")


def _copy_colr(target: ttLib.TTFont, donor: ttLib.TTFont):
    # Copy all glyphs used by COLR over
    _glyphs_to_copy = set()
    new_glyphorder = list(target.getGlyphOrder())

    def _collect_glyphs(paint):
        if paint.Format == ot.PaintFormat.PaintGlyph:
            _glyphs_to_copy.add(paint.Glyph)

    for record in donor["COLR"].table.BaseGlyphList.BaseGlyphPaintRecord:
        record.Paint.traverse(donor["COLR"].table, _collect_glyphs)

    for glyph_name in _glyphs_to_copy:
        print("Copy glyph", glyph_name)
        target["glyf"].glyphs[glyph_name] = donor["glyf"].glyphs[glyph_name]
        target["hmtx"].metrics[glyph_name] = donor["hmtx"].metrics[glyph_name]

        # .notdef in particular likely to be in both
        if glyph_name not in new_glyphorder:
            new_glyphorder.append(glyph_name)

    target.setGlyphOrder(new_glyphorder)
    # glyf fails internal checks if not advised of new glyph orderings
    target["glyf"].setGlyphOrder(new_glyphorder)

    target["CPAL"] = donor["CPAL"]
    target["COLR"] = donor["COLR"]


def main(argv):
    target = ttLib.TTFont(FLAGS.target_font)
    donor = ttLib.TTFont(FLAGS.donor_font)

    if FLAGS.color_table == "COLR":
        _copy_colr(target, donor)
    else:
        raise ValueError(f"Unsupported color table '{FLAGS.color_table}'")

    target.save(FLAGS.output_file)
    logging.info("Wrote %s", FLAGS.output_file)


if __name__ == "__main__":
    flags.mark_flag_as_required("target_font")
    flags.mark_flag_as_required("donor_font")
    flags.mark_flag_as_required("color_table")
    flags.mark_flag_as_required("output_file")
    app.run(main)
