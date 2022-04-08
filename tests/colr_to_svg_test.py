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

from fontTools.colorLib.builder import buildCPAL, LayerListBuilder
from fontTools import ttLib
from fontTools.ttLib.tables import _g_l_y_f
from fontTools.ttLib.ttFont import newTable
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib.tables import otTables as ot
from lxml import etree
from nanoemoji.colr_to_svg import _colr_v1_paint_to_svg, _new_reuse_cache
from picosvg.svg import SVG
from picosvg.svg_transform import Affine2D
import pytest
from test_helper import svg_diff
import textwrap


def _draw_box(pen):
    pen.moveTo((10, 10))
    pen.lineTo((90, 10))
    pen.lineTo((90, 90))
    pen.lineTo((10, 90))
    pen.closePath()


def _build(cls, source) -> ot.Paint:
    return LayerListBuilder().tableBuilder.build(cls, source)


def _buildPaint(source) -> ot.Paint:
    return LayerListBuilder().buildPaint(source)


@pytest.mark.parametrize(
    "paint_def, glyph_defs, expected_svg",
    [
        (
            # Solid filled box
            (
                ot.PaintFormat.PaintGlyph,
                (ot.PaintFormat.PaintSolid, 0),
                "box",
            ),
            {"box": _draw_box},
            """
            <svg xmlns="http://www.w3.org/2000/svg">
              <defs/>
              <path d="M10,10 L90,10 L90,90 L10,90 Z"/>
            </svg>
            """,
        ),
    ],
)
def test_colr_v1_paint_to_svg(paint_def, glyph_defs, expected_svg):
    paint = _build(ot.Paint, paint_def)
    actual_svg = SVG.fromstring('<svg xmlns="http://www.w3.org/2000/svg"><defs/></svg>')
    expected_svg = SVG.fromstring(textwrap.dedent(expected_svg))

    # create a minimal font to play with
    font = ttLib.TTFont()
    glyf_table = font["glyf"] = newTable("glyf")
    glyf_table.glyphs = {".notdef": _g_l_y_f.Glyph()}
    hmtx_table = font["hmtx"] = newTable("hmtx")
    hmtx_table.metrics = {}
    head_table = font["head"] = newTable("head")
    head_table.unitsPerEm = 100
    maxp_table = font["maxp"] = newTable("maxp")
    maxp_table.numGlyphs = 1

    # provide some simple shapes to play with
    for glyph_name, draw_fn in glyph_defs.items():
        font.setGlyphOrder(font.getGlyphOrder() + [glyph_name])
        pen = TTGlyphPen(None)
        draw_fn(pen)
        glyph = pen.glyph()
        # Add to glyf
        glyf_table.glyphs[glyph_name] = glyph

        # setup hmtx
        glyph.recalcBounds(glyf_table)
        hmtx_table.metrics[glyph_name] = (head_table.unitsPerEm, glyph.xMin)

    # palette 0: black, white
    palettes = [
        [(0, 0, 0, 1.0), (1, 1, 1, 1.0)],
        [(0.1, 0.2, 0.3, 0.6), (0.4, 0.5, 0.6, 0.6)],
        [(0.1, 0.2, 0.3, 0.3), (0.4, 0.5, 0.6, 0.3)],
    ]
    font["CPAL"] = buildCPAL(palettes)

    _colr_v1_paint_to_svg(
        font,
        font.getGlyphSet(),
        actual_svg.svg_root,
        actual_svg.xpath_one("//svg:defs"),
        Affine2D.identity(),
        paint,
        _new_reuse_cache(),
    )

    svg_diff(actual_svg, expected_svg)
