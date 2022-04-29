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
import copy
from fontTools.ttLib.tables import otTables as ot
from fontTools.ttLib.tables.C_B_D_T_ import cbdt_bitmap_format_17 as CbdtBitmapFormat17
from fontTools import ttLib
from nanoemoji import bitmap_tables
from nanoemoji.colr import paints_of_type
from nanoemoji.reorder_glyphs import reorder_glyphs
from nanoemoji.util import load_fully
import os
from pathlib import Path
from typing import Iterable, List, Mapping, NamedTuple, Tuple


FLAGS = flags.FLAGS


flags.DEFINE_string("target_font", None, "Font assets are copied into.")
flags.DEFINE_string("donor_font", None, "Font from which assets are copied.")
flags.DEFINE_string("color_table", None, "The color table to copy.")


class CbdtGlyphInfo(NamedTuple):
    data: CbdtBitmapFormat17
    size: int


def _copy_colr(target: ttLib.TTFont, donor: ttLib.TTFont):
    # Copy all glyphs used by COLR over
    glyphs_to_copy = sorted(
        {p.Glyph for p in paints_of_type(donor, ot.PaintFormat.PaintGlyph)}
    )

    # We avoid using the glyf table's `__setitem__` for it appends to the TTFont's
    # glyphOrder list without also invalidating the {glyphNames:glyphID} cache,
    # which means TTFont.getGlyphID could return incorrect result.
    # Instead we set the new glyphs directly inside the glyf's `glyphs` dict and
    # call TTFont.setGlyphOrder at the end, which automatically triggers a rebuild
    # of glyphID cache.
    # https://github.com/fonttools/fonttools/issues/2605
    target_glyphs = target["glyf"].glyphs
    for glyph_name in glyphs_to_copy:
        target_glyphs[glyph_name] = donor["glyf"][glyph_name]

        if glyph_name in target["hmtx"].metrics:
            assert (
                target["hmtx"][glyph_name] == donor["hmtx"][glyph_name]
            ), f"Unexpected change in metrics for {glyph_name}"
        else:
            # new glyph, new metrics
            target["hmtx"][glyph_name] = donor["hmtx"][glyph_name]

    target.setGlyphOrder(target.getGlyphOrder() + glyphs_to_copy)

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

    reorder_glyphs(target, new_glyph_order)
    target["SVG "] = donor["SVG "]


def _cbdt_data_and_sizes(ttfont: ttLib.TTFont) -> Mapping[str, CbdtGlyphInfo]:
    data = {}
    for strike_data in ttfont["CBDT"].strikeData:
        data.update(strike_data)

    sizes = {}
    for strike in ttfont["CBLC"].strikes:
        for sub_table in strike.indexSubTables:
            for name, (start, end) in zip(sub_table.names, sub_table.locations):
                sizes[name] = end - start

    assert data.keys() == sizes.keys(), f"{data.keys()} != {sizes.keys()}"

    return {
        glyph_name: CbdtGlyphInfo(data[glyph_name], sizes[glyph_name])
        for glyph_name in data
    }


def _copy_cbdt(target: ttLib.TTFont, donor: ttLib.TTFont):
    cbdt_glyph_info = _cbdt_data_and_sizes(donor)

    # reorder the bitmap table to match the targets glyph order
    # we only support square bitmaps so the strikes are all the same
    # other than glyph names so we can just construct a new
    # order that matches that of target
    donor_order = list(cbdt_glyph_info.keys())
    only_in_donor = set(donor_order) - set(target.getGlyphOrder())
    # confirm our core assumption that we successfully held glyph names stable
    if only_in_donor:
        raise ValueError(
            f"Donor glyph names do not exist in target: {sorted(only_in_donor)}"
        )
    new_order = sorted(donor_order, key=target.getGlyphID)

    # now we know the desired order, reshard into runs
    # TODO duplicative of make_cbdt_table
    # take the first strike as a template, then wipe out strikes and data
    # so we can build it up again in a potentially different glyph order
    strike_template = donor["CBLC"].strikes[0]
    clbc_index_template = strike_template.indexSubTables[0]
    strike_template.indexSubTables = []
    cblc = donor["CBLC"]
    cblc.strikes = []
    cbdt = donor["CBDT"]
    cbdt.strikeData = []

    data_offset = bitmap_tables.CBDT_HEADER_SIZE
    while new_order:
        # grab the next run w/consecutive gids
        min_gid = target.getGlyphID(new_order[0])
        end = 1
        while (
            len(new_order) > end
            and target.getGlyphID(new_order[end])
            == target.getGlyphID(new_order[end - 1]) + 1
        ):
            end += 1
        glyph_run = new_order[:end]
        new_order = new_order[end:]
        max_gid = target.getGlyphID(glyph_run[-1])

        strike = copy.deepcopy(strike_template)
        strike.bitmapSizeTable.min_gid = min_gid
        strike.bitmapSizeTable.max_gid = max_gid

        max_width = max(cbdt_glyph_info[gn].data.metrics.Advance for gn in glyph_run)
        strike.bitmapSizeTable.hori.widthMax = max_width
        strike.bitmapSizeTable.vert.widthMax = max_width

        clbc_index = copy.deepcopy(clbc_index_template)
        clbc_index.names = glyph_run
        clbc_index.locations = []
        for glyph_name in glyph_run:
            clbc_index.locations.append(
                (data_offset, data_offset + cbdt_glyph_info[glyph_name].size)
            )
            data_offset = clbc_index.locations[-1][-1]

        strike.indexSubTables = [clbc_index]
        cblc.strikes.append(strike)
        cbdt.strikeData.append({gn: cbdt_glyph_info[gn].data for gn in glyph_run})

    target["CBDT"] = cbdt
    target["CBLC"] = cblc


def main(argv):
    target = load_fully(Path(FLAGS.target_font))
    donor = load_fully(Path(FLAGS.donor_font))

    donation = FLAGS.color_table.lower().strip()
    if donation == "colr":
        _copy_colr(target, donor)
    elif donation == "svg":
        _copy_svg(target, donor)
    elif donation == "cbdt":
        _copy_cbdt(target, donor)
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
