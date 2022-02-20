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

"""Helps with bitmap tables."""
from fontTools import ttLib
from fontTools.ttLib.tables.BitmapGlyphMetrics import BigGlyphMetrics, SmallGlyphMetrics
from fontTools.ttLib.tables.sbixGlyph import Glyph as SbixGlyph
from fontTools.ttLib.tables.sbixStrike import Strike as SbixStrike
from fontTools.ttLib.tables.E_B_L_C_ import (
    Strike as CblcStrike,
    SbitLineMetrics as CblcSbitLineMetrics,
    eblc_index_sub_table_1 as CblcIndexSubTable1,
    eblc_index_sub_table_2 as CblcIndexSubTable2,
)
from fontTools.ttLib.tables.C_B_D_T_ import cbdt_bitmap_format_17 as CbdtBitmapFormat17
from functools import reduce
from nanoemoji.config import FontConfig
from nanoemoji.color_glyph import ColorGlyph
from typing import (
    List,
    NamedTuple,
    Sequence,
    Tuple,
)
import sys


_INT8_RANGE = range(-128, 127 + 1)
_UINT8_RANGE = range(0, 255 + 1)

# https://docs.microsoft.com/en-us/typography/opentype/spec/cbdt#table-structure
_CBDT_HEADER_SIZE = 4

# https://docs.microsoft.com/en-us/typography/opentype/spec/cbdt#format-17-small-metrics-png-image-data
_CBDT_SMALL_METRIC_PNGS = 17

# SmallGlyphMetrics(5) + dataLen(4)
_CBDT_SMALL_METRIC_PNG_HEADER_SIZE = 5 + 4


class BitmapMetrics(NamedTuple):
    x_offset: int
    y_offset: int
    line_height: int
    line_ascent: int

    @classmethod
    def create(cls, config: FontConfig, ppem: int) -> "BitmapMetrics":
        # https://github.com/googlefonts/noto-emoji/blob/9a5261d871451f9b5183c93483cbd68ed916b1e9/third_party/color_emoji/emoji_builder.py#L109
        ascent = config.ascender
        descent = -config.descender

        line_height = round((ascent + descent) * ppem / float(config.upem))
        line_ascent = ascent * ppem / float(config.upem)

        metrics = BitmapMetrics(
            x_offset=max(
                round((_width_in_pixels(config) - config.bitmap_resolution) / 2), 0
            ),
            y_offset=round(
                line_ascent - 0.5 * (line_height - config.bitmap_resolution)
            ),
            line_height=line_height,
            line_ascent=round(line_ascent),
        )

        return metrics


def _width_in_pixels(config: FontConfig) -> int:
    return round(
        config.bitmap_resolution * config.width / (config.ascender - config.descender)
    )


# https://github.com/googlefonts/noto-emoji/blob/9a5261d871451f9b5183c93483cbd68ed916b1e9/third_party/color_emoji/emoji_builder.py#L53
def _ppem(config: FontConfig, advance: int) -> int:
    return round(_width_in_pixels(config) * config.upem / advance)


def _advance(ttfont: ttLib.TTFont, color_glyphs: Sequence[ColorGlyph]) -> int:
    # let's go ahead and fail miserably if advances are not all the same
    # proportional bitmaps can wait for a second pass :)
    advances = {
        ttfont["hmtx"].metrics[ttfont.getGlyphName(c.glyph_id)][0] for c in color_glyphs
    }
    assert len(advances) == 1, "Proportional bitmaps not supported yet"
    return next(iter(advances))


def _cbdt_record_size(image_format: int, image_data: bytes) -> int:
    assert image_format == _CBDT_SMALL_METRIC_PNGS, "Unrecognized format"
    return _CBDT_SMALL_METRIC_PNG_HEADER_SIZE + len(image_data)


def _cbdt_bitmapdata_offsets(
    image_format: int, color_glyphs: Sequence[ColorGlyph]
) -> List[Tuple[int, int]]:
    # TODO is this right? - feels dumb. But ... compile crashes if locations are unknown.
    offsets = []
    offset = _CBDT_HEADER_SIZE
    for color_glyph in color_glyphs:
        offsets.append(offset)
        offset += _cbdt_record_size(image_format, color_glyph.bitmap)
    offsets.append(offset)  # capture end of stream
    return list(zip(offsets, offsets[1:]))


def _cbdt_bitmap_data(
    config: FontConfig, metrics: BitmapMetrics, image_data: bytes
) -> CbdtBitmapFormat17:

    bitmap_data = CbdtBitmapFormat17(b"", None)
    bitmap_data.metrics = SmallGlyphMetrics()
    bitmap_data.metrics.height = config.bitmap_resolution
    bitmap_data.metrics.width = config.bitmap_resolution
    # center within advance
    bitmap_data.metrics.BearingX = metrics.x_offset
    bitmap_data.metrics.BearingY = metrics.y_offset
    bitmap_data.metrics.Advance = _width_in_pixels(config)
    bitmap_data.imageData = image_data
    return bitmap_data


def make_sbix_table(
    config: FontConfig,
    ttfont: ttLib.TTFont,
    color_glyphs: Sequence[ColorGlyph],
):

    sbix = ttLib.newTable("sbix")
    ttfont[sbix.tableTag] = sbix

    ppem = _ppem(config, _advance(ttfont, color_glyphs))

    strike = SbixStrike()
    strike.ppem = ppem
    strike.resolution = 72  # pixels per inch
    sbix.strikes[strike.ppem] = strike

    metrics = BitmapMetrics.create(config, strike.ppem)

    for color_glyph in color_glyphs:
        # TODO: if we've seen these bytes before set graphicType "dupe", referenceGlyphName <name of glyph>
        image_data = color_glyph.bitmap

        glyph_name = ttfont.getGlyphName(color_glyph.glyph_id)
        glyph = SbixGlyph(
            graphicType="png",
            glyphName=glyph_name,
            imageData=image_data,
            originOffsetX=metrics.x_offset,
            originOffsetY=metrics.line_ascent - metrics.line_height,
        )
        strike.glyphs[glyph_name] = glyph


# Ref https://github.com/googlefonts/noto-emoji/blob/main/third_party/color_emoji/emoji_builder.py
def make_cbdt_table(
    config: FontConfig,
    ttfont: ttLib.TTFont,
    color_glyphs: Sequence[ColorGlyph],
):

    # bitmap tables don't like it when we're out of order
    color_glyphs = sorted(color_glyphs, key=lambda c: c.glyph_id)

    min_gid, max_gid = color_glyphs[0].glyph_id, color_glyphs[-1].glyph_id
    assert max_gid - min_gid + 1 == len(
        color_glyphs
    ), "Below assumes color gyphs gids are consecutive"

    advance = _advance(ttfont, color_glyphs)
    ppem = _ppem(config, advance)

    cbdt = ttLib.newTable("CBDT")
    ttfont[cbdt.tableTag] = cbdt

    cblc = ttLib.newTable("CBLC")
    ttfont[cblc.tableTag] = cblc

    cblc.version = cbdt.version = 3.0

    strike = CblcStrike()
    strike.bitmapSizeTable.startGlyphIndex = min_gid
    strike.bitmapSizeTable.endGlyphIndex = max_gid
    strike.bitmapSizeTable.ppemX = ppem
    strike.bitmapSizeTable.ppemY = ppem
    strike.bitmapSizeTable.colorRef = 0
    strike.bitmapSizeTable.bitDepth = 32
    # https://docs.microsoft.com/en-us/typography/opentype/spec/eblc#bitmapFlags
    strike.bitmapSizeTable.flags = 1  # HORIZONTAL_METRICS

    line_metrics = CblcSbitLineMetrics()
    line_metrics.caretSlopeNumerator = 0
    line_metrics.caretSlopeDenominator = 0
    line_metrics.caretSlopeDenominator = 0
    line_metrics.caretOffset = 0
    line_metrics.minOriginSB = 0
    line_metrics.minAdvanceSB = 0
    line_metrics.maxBeforeBL = 0
    line_metrics.minAfterBL = 0
    line_metrics.pad1 = 0
    line_metrics.pad2 = 0

    metrics = BitmapMetrics.create(config, ppem)
    # The FontTools errors when values are out of bounds are a bit nasty
    # so check here for earlier and more helpful termination
    assert (
        config.bitmap_resolution in _UINT8_RANGE
    ), f"bitmap_resolution out of bounds: {config.bitmap_resolution}"
    assert metrics.y_offset in _INT8_RANGE, f"y_offset out of bounds: {metrics}"

    line_metrics.ascender = round(config.ascender * ppem / config.upem)
    line_metrics.descender = -(metrics.line_height - line_metrics.ascender)
    line_metrics.widthMax = _width_in_pixels(config)

    strike.bitmapSizeTable.hori = line_metrics
    strike.bitmapSizeTable.vert = line_metrics

    # Simplifying assumption: identical metrics
    # https://docs.microsoft.com/en-us/typography/opentype/spec/eblc#indexsubtables

    # Apparently you cannot build a CBLC index subtable w/o providing bytes & font?!
    # If we build from empty bytes and fill in the fields all is well
    index_subtable = CblcIndexSubTable1(b"", ttfont)
    # CBLC image format matches https://docs.microsoft.com/en-us/typography/opentype/spec/cbdt#glyph-bitmap-data-formats
    # We are using small metrics and PNG images exclusively for now
    index_subtable.indexFormat = 1
    index_subtable.imageFormat = _CBDT_SMALL_METRIC_PNGS
    index_subtable.imageSize = config.bitmap_resolution
    index_subtable.names = [ttfont.getGlyphName(c.glyph_id) for c in color_glyphs]
    index_subtable.locations = _cbdt_bitmapdata_offsets(
        index_subtable.imageFormat, color_glyphs
    )

    strike.indexSubTables = [index_subtable]
    cblc.strikes = [strike]

    # Now register all the data
    cbdt.strikeData = [
        {
            ttfont.getGlyphName(c.glyph_id): _cbdt_bitmap_data(
                config, metrics, c.bitmap
            )
            for c in color_glyphs
        }
    ]
