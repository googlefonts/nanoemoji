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

from fontTools.colorLib.builder import buildCPAL, buildColrV1, LayerListBuilder
from fontTools import ttLib
from fontTools.ttLib.tables import _g_l_y_f
from fontTools.ttLib.ttFont import newTable
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib.tables import otTables as ot
from lxml import etree
from nanoemoji.colr_to_svg import _colr_v1_paint_to_svg, _new_reuse_cache
from nanoemoji.util import only
from picosvg.svg import SVG
from picosvg.svg_transform import Affine2D
import pytest
from test_helper import svg_diff
import textwrap


def _draw_box(pen):
    x1, y1 = (10, 10)
    x2, y2 = (90, 90)
    pen.moveTo((x1, y1))
    pen.lineTo((x2, y1))
    pen.lineTo((x2, y2))
    pen.lineTo((x1, y2))
    pen.closePath()


def _build(cls, source) -> ot.Paint:
    return LayerListBuilder().tableBuilder.build(cls, source)


def _buildPaint(source) -> ot.Paint:
    return LayerListBuilder().buildPaint(source)


@pytest.mark.parametrize(
    "glyph_to_convert, color_glyphs, monochrome_glyphs, expected_svg",
    [
        # Solid filled box
        (
            "color_box",
            {
                "color_box": (
                    ot.PaintFormat.PaintGlyph,
                    (ot.PaintFormat.PaintSolid, 0),
                    "box",
                ),
            },
            {"box": _draw_box},
            """
            <svg xmlns="http://www.w3.org/2000/svg">
              <defs/>
              <path d="M10,10 L90,10 L90,90 L10,90 Z"/>
            </svg>
            """,
        ),
        # Paint colr glyph
        (
            "paint_colr_glyph",
            {
                "paint_colr_glyph": (ot.PaintFormat.PaintColrGlyph, "color_box"),
                "color_box": (
                    ot.PaintFormat.PaintGlyph,
                    (ot.PaintFormat.PaintSolid, 0),
                    "box",
                ),
            },
            {"box": _draw_box},
            """
            <svg xmlns="http://www.w3.org/2000/svg">
              <defs/>
              <path d="M10,10 L90,10 L90,90 L10,90 Z"/>
            </svg>
            """,
        ),
        # PaintComposite as nanoemoji uses it for group opacity
        (
            "composite",
            {
                "composite": {
                    "Format": int(ot.PaintFormat.PaintComposite),
                    "CompositeMode": "src_in",
                    "SourcePaint": (
                        ot.PaintFormat.PaintColrLayers,
                        [
                            (
                                ot.PaintFormat.PaintGlyph,
                                (ot.PaintFormat.PaintSolid, 0, 0.8),
                                "box",
                            ),
                            (
                                ot.PaintFormat.PaintTranslate,
                                (
                                    ot.PaintFormat.PaintGlyph,
                                    (ot.PaintFormat.PaintSolid, 0),
                                    "box",
                                ),
                                10,
                                10,
                            ),
                        ],
                    ),
                    "BackdropPaint": {
                        "Format": ot.PaintFormat.PaintSolid,
                        "PaletteIndex": 0,
                        "Alpha": 0.5,
                    },
                },
            },
            {"box": _draw_box},
            """
            <svg xmlns="http://www.w3.org/2000/svg">
              <defs/>
              <g opacity="0.5">
                <path opacity="0.8" d="M10,10 L90,10 L90,90 L10,90 Z"/>
                <path transform="translate(10, 10)" d="M10,10 L90,10 L90,90 L10,90 Z"/>
              </g>
            </svg>
            """,
        ),
        # other kinds of PaintComposite are dropped for now, only BackdropPaint is kept
        # https://github.com/googlefonts/nanoemoji/issues/409
        (
            "composite",
            {
                "composite": {
                    "Format": ot.PaintFormat.PaintComposite,
                    "CompositeMode": "soft_light",
                    "SourcePaint": {
                        "Format": ot.PaintFormat.PaintLinearGradient,
                        "ColorLine": {
                            "Extend": "pad",
                            "ColorStop": [(0.0, 1, 0.5), (0.5, 2, 0.5), (1.0, 3, 0.5)],
                        },
                        "x0": 47,
                        "y0": 790,
                        "x1": 890,
                        "y1": -342,
                        "x2": -1085,
                        "y2": -53,
                    },
                    "BackdropPaint": (
                        ot.PaintFormat.PaintGlyph,
                        (ot.PaintFormat.PaintSolid, 0),
                        "box",
                    ),
                },
            },
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
def test_colr_v1_paint_to_svg(
    glyph_to_convert, color_glyphs, monochrome_glyphs, expected_svg
):
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
    colr_table = font["COLR"] = newTable("COLR")
    colr_table.table = ot.COLR()

    # provide some simple shapes to play with
    for glyph_name, draw_fn in monochrome_glyphs.items():
        font.setGlyphOrder(font.getGlyphOrder() + [glyph_name])
        pen = TTGlyphPen(None)
        draw_fn(pen)
        glyph = pen.glyph()
        # Add to glyf
        glyf_table.glyphs[glyph_name] = glyph

        # setup hmtx
        glyph.recalcBounds(glyf_table)
        hmtx_table.metrics[glyph_name] = (head_table.unitsPerEm, glyph.xMin)

    print(hmtx_table.metrics)

    # palette 0: black, blue
    palettes = [
        [(0, 0, 0, 1.0), (0, 0, 1, 1.0)],
    ]
    font["CPAL"] = buildCPAL(palettes)

    layers, base_glyphs = buildColrV1(color_glyphs)
    colr_table.table.LayerList = layers
    colr_table.table.BaseGlyphList = base_glyphs
    paint = only(
        g.Paint
        for g in base_glyphs.BaseGlyphPaintRecord
        if g.BaseGlyph == glyph_to_convert
    )

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
