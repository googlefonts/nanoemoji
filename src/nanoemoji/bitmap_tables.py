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

"""Helps with bitmap tables.

CBDT inspired by https://github.com/googlefonts/noto-emoji/blob/main/third_party/color_emoji/emoji_builder.py.
"""
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
from io import BytesIO
from nanoemoji.config import FontConfig
from nanoemoji.color_glyph import ColorGlyph
from nanoemoji.png import PNG
from nanoemoji.util import only
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
CBDT_HEADER_SIZE = 4

# https://docs.microsoft.com/en-us/typography/opentype/spec/cbdt#format-17-small-metrics-png-image-data
_CBDT_SMALL_METRIC_PNGS = 17

# SmallGlyphMetrics(5) + dataLen(4)
_CBDT_SMALL_METRIC_PNG_HEADER_SIZE = 5 + 4


def _nudge_into_range(arange: range, value: int, max_move: int = 1) -> int:
    if value in arange:
        return value
    if value > max(arange) and value - max_move <= max(arange):
        return max(arange)
    if value < min(arange) and value + max_move >= min(arange):
        return min(arange)
    return value


class BitmapMetrics(NamedTuple):
    x_offset: int
    y_offset: int
    line_height: int
    line_ascent: int

    @classmethod
    def create(cls, config: FontConfig, image_data: PNG, ppem: int) -> "BitmapMetrics":
        ascent = config.ascender
        descent = -config.descender

        line_height = round((ascent + descent) * ppem / float(config.upem))
        line_ascent = ascent * ppem / float(config.upem)

        # center within advance
        metrics = BitmapMetrics(
            x_offset=_nudge_into_range(
                _INT8_RANGE,
                max(
                    round(
                        (
                            _width_in_pixels(config, image_data)
                            - config.bitmap_resolution
                        )
                        / 2
                    ),
                    0,
                ),
            ),
            y_offset=_nudge_into_range(
                _INT8_RANGE,
                round(line_ascent - 0.5 * (line_height - config.bitmap_resolution)),
            ),
            line_height=line_height,
            line_ascent=round(line_ascent),
        )

        # The FontTools errors when values are out of bounds are a bit nasty
        # so check here for earlier and more helpful termination
        assert (
            config.bitmap_resolution in _UINT8_RANGE
        ), f"bitmap_resolution out of bounds: {config.bitmap_resolution}"
        assert metrics.y_offset in _INT8_RANGE, f"y_offset out of bounds: {metrics}"

        return metrics


def _pixels_to_funits(config: FontConfig, bitmap_pixel_height: int) -> Tuple[int, int]:
    # the bitmap is vertically scaled to fill the space desc to asc
    # this gives us a ratio between pixels and upem
    funits = config.ascender - config.descender
    return (bitmap_pixel_height, funits)


def _width_in_pixels(config: FontConfig, image_data: PNG) -> int:
    pixels, funits = _pixels_to_funits(config, image_data.size[1])

    width_funits = image_data.size[0] * funits / pixels
    width_funits = max(config.width, width_funits)

    assert width_funits > 0
    return round(width_funits * pixels / funits)


def _ppem(config: FontConfig, bitmap_pixel_height: int) -> int:
    pixels, funits = _pixels_to_funits(config, bitmap_pixel_height)
    return round(config.upem * pixels / funits)


def _cbdt_record_size(image_format: int, image_data: bytes) -> int:
    assert image_format == _CBDT_SMALL_METRIC_PNGS, "Unrecognized format"
    return _CBDT_SMALL_METRIC_PNG_HEADER_SIZE + len(image_data)


def _cbdt_bitmapdata_offsets(
    initial_offset: int, image_format: int, color_glyphs: Sequence[ColorGlyph]
) -> List[Tuple[int, int]]:
    # TODO is this right? - feels dumb. But ... compile crashes if locations are unknown.
    offsets = []
    offset = initial_offset
    for color_glyph in color_glyphs:
        offsets.append(offset)
        offset += _cbdt_record_size(image_format, color_glyph.bitmap)
    offsets.append(offset)  # capture end of stream
    return list(zip(offsets, offsets[1:]))


def _cbdt_bitmap_data(
    config: FontConfig, metrics: BitmapMetrics, image_data: PNG
) -> CbdtBitmapFormat17:

    bitmap_data = CbdtBitmapFormat17(b"", None)
    bitmap_data.metrics = SmallGlyphMetrics()
    bitmap_data.metrics.width, bitmap_data.metrics.height = image_data.size
    bitmap_data.metrics.BearingX = metrics.x_offset
    bitmap_data.metrics.BearingY = metrics.y_offset
    bitmap_data.metrics.Advance = _width_in_pixels(config, image_data)
    bitmap_data.imageData = image_data
    return bitmap_data


def make_sbix_table(
    config: FontConfig,
    ttfont: ttLib.TTFont,
    color_glyphs: Sequence[ColorGlyph],
):

    sbix = ttLib.newTable("sbix")
    ttfont[sbix.tableTag] = sbix

    bitmap_pixel_height = only({c.bitmap.size[1] for c in color_glyphs})
    ppem = _ppem(config, bitmap_pixel_height)

    strike = SbixStrike()
    strike.ppem = ppem
    strike.resolution = 72  # pixels per inch
    sbix.strikes[strike.ppem] = strike

    for color_glyph in color_glyphs:
        # TODO: if we've seen these bytes before set graphicType "dupe", referenceGlyphName <name of glyph>
        image_data = color_glyph.bitmap
        metrics = BitmapMetrics.create(config, image_data, strike.ppem)

        glyph_name = ttfont.getGlyphName(color_glyph.glyph_id)
        glyph = SbixGlyph(
            graphicType="png",
            glyphName=glyph_name,
            imageData=image_data,
            originOffsetX=metrics.x_offset,
            originOffsetY=metrics.line_ascent - metrics.line_height,
        )
        strike.glyphs[glyph_name] = glyph


def _make_cbdt_strike(
    config: FontConfig,
    ttfont: ttLib.TTFont,
    data_offset: int,
    color_glyphs: Sequence[ColorGlyph],
):
    min_gid, max_gid = color_glyphs[0].glyph_id, color_glyphs[-1].glyph_id
    assert max_gid - min_gid + 1 == len(
        color_glyphs
    ), "Below assumes color gyphs gids are consecutive"

    bitmap_pixel_height = only({c.bitmap.size[1] for c in color_glyphs})
    ppem = _ppem(config, bitmap_pixel_height)

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

    metrics = {
        c.glyph_id: BitmapMetrics.create(config, c.bitmap, ppem) for c in color_glyphs
    }
    data = {
        ttfont.getGlyphName(c.glyph_id): _cbdt_bitmap_data(
            config, metrics[c.glyph_id], c.bitmap
        )
        for c in color_glyphs
    }

    line_height = only({m.line_height for m in metrics.values()})

    line_metrics.ascender = round(config.ascender * ppem / config.upem)
    line_metrics.descender = -(line_height - line_metrics.ascender)
    line_metrics.widthMax = max(d.metrics.Advance for d in data.values())

    strike.bitmapSizeTable.hori = line_metrics
    strike.bitmapSizeTable.vert = line_metrics

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
        data_offset, index_subtable.imageFormat, color_glyphs
    )

    strike.indexSubTables = [index_subtable]

    return strike, data


def raise_if_too_big_for_cbdt(color_glyphs: Sequence[ColorGlyph]):
    too_big = sorted(
        (c for c in color_glyphs if max(c.bitmap.size) not in _UINT8_RANGE),
        key=lambda c: c.bitmap_filename,
    )
    if not too_big:
        return
    raise ValueError(
        "Bitmap is too big for CBDT, try lowering bitmap_resolution: "
        + ",".join(c.bitmap_filename for c in too_big)
    )


def make_cbdt_table(
    config: FontConfig,
    ttfont: ttLib.TTFont,
    color_glyphs: Sequence[ColorGlyph],
):
    # CBDT is a wee bit limited in pixel size
    raise_if_too_big_for_cbdt(color_glyphs)

    # bitmap tables don't like it when we're out of order
    color_glyphs = sorted(color_glyphs, key=lambda c: c.glyph_id)

    cbdt = ttLib.newTable("CBDT")
    ttfont[cbdt.tableTag] = cbdt

    cblc = ttLib.newTable("CBLC")
    ttfont[cblc.tableTag] = cblc

    cblc.version = cbdt.version = 3.0

    cblc.strikes = []
    cbdt.strikeData = []

    data_offset = CBDT_HEADER_SIZE

    while color_glyphs:
        # grab the next run w/consecutive gids
        min_gid = color_glyphs[0].glyph_id
        end = 1
        while (
            len(color_glyphs) > end
            and color_glyphs[end].glyph_id == color_glyphs[end - 1].glyph_id + 1
        ):
            end += 1
        color_glyph_run = color_glyphs[:end]
        color_glyphs = color_glyphs[end:]

        strike, data = _make_cbdt_strike(config, ttfont, data_offset, color_glyph_run)
        for sub_table in strike.indexSubTables:
            data_offset = max(sub_table.locations[-1][-1], data_offset)

        cblc.strikes.append(strike)
        cbdt.strikeData.append(data)
