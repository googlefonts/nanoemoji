# Copyright 2020 Google LLC
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

from nanoemoji import colors
from nanoemoji import color_glyph
from nanoemoji.paint import (
    ColorStop,
    Extend,
    PaintSolid,
    PaintLinearGradient,
    PaintRadialGradient,
    PaintGlyph,
    PaintColrGlyph,
    PaintTransform,
    PaintComposite,
    PaintColrLayers,
)
from nanoemoji.svg import (
    _svg_matrix,
    _apply_solid_paint,
    _apply_gradient_paint,
    _map_gradient_coordinates,
    _GradientPaint,
)
from nanoemoji.svg_path import SVGPathPen
from picosvg.svg import SVG
from picosvg.svg_meta import ntos
from picosvg.svg_transform import Affine2D
from fontTools import ttLib
from picosvg.geometric_types import Point, Rect
import test_helper
from lxml import etree
from typing import Any, Dict, Mapping, Optional
from fontTools.pens import transformPen
from fontTools.ttLib.tables import otTables


_GRADIENT_PAINT_FORMATS = (PaintLinearGradient.format, PaintRadialGradient.format)


def _map_font_space_to_viewbox(
    view_box: Rect, ascender: int, descender: int, width: int
) -> Affine2D:
    return color_glyph.map_viewbox_to_font_space(
        view_box, ascender, descender, width, Affine2D.identity()
    ).inverse()


def _svg_root(view_box: Rect) -> etree.Element:
    svg_tree = etree.parse(
        str(test_helper.locate_test_file("colr_to_svg_template.svg"))
    )
    svg_root = svg_tree.getroot()
    vbox = (view_box.x, view_box.y, view_box.w, view_box.h)
    svg_root.attrib["viewBox"] = " ".join(ntos(v) for v in vbox)
    return svg_root


def _draw_svg_path(
    svg_path: etree.Element,
    glyph_set: ttLib.ttFont._TTGlyphSet,
    glyph_name: str,
    font_to_vbox: Affine2D,
):
    # use glyph set to resolve references in composite glyphs
    svg_pen = SVGPathPen(glyph_set)
    # wrap svg pen with "filter" pen mapping coordinates from UPEM to SVG space
    transform_pen = transformPen.TransformPen(svg_pen, font_to_vbox)

    glyph = glyph_set[glyph_name]
    glyph.draw(transform_pen)

    svg_path.attrib["d"] = svg_pen.path.d


def _color(ttfont: ttLib.TTFont, palette_index, alpha=1.0) -> colors.Color:
    cpal_color = ttfont["CPAL"].palettes[0][palette_index]
    return colors.Color(
        red=cpal_color.red,
        green=cpal_color.green,
        blue=cpal_color.blue,
        alpha=alpha * cpal_color.alpha / 255,
    )


def _gradient_paint(ttfont: ttLib.TTFont, ot_paint: otTables.Paint) -> _GradientPaint:
    stops = [
        ColorStop(
            stop.StopOffset,
            _color(ttfont, stop.Color.PaletteIndex, stop.Color.Alpha),
        )
        for stop in ot_paint.ColorLine.ColorStop
    ]
    extend = Extend((ot_paint.ColorLine.Extend,))
    if ot_paint.Format == PaintLinearGradient.format:
        return PaintLinearGradient(
            stops=stops,
            extend=extend,
            p0=Point(ot_paint.x0, ot_paint.y0),
            p1=Point(ot_paint.x1, ot_paint.y1),
            p2=Point(ot_paint.x2, ot_paint.y2),
        )
    elif ot_paint.Format == PaintRadialGradient.format:
        return PaintRadialGradient(
            stops=stops,
            extend=extend,
            c0=Point(ot_paint.x0, ot_paint.y0),
            c1=Point(ot_paint.x1, ot_paint.y1),
            r0=ot_paint.r0,
            r1=ot_paint.r1,
        )
    else:
        raise ValueError(
            f"Expected one of Paint formats {_GRADIENT_PAINT_FORMATS}; "
            f"found {ot_paint.Format}"
        )


def _apply_solid_ot_paint(
    svg_path: etree.Element,
    ttfont: ttLib.TTFont,
    ot_paint: otTables.Paint,
):
    color = _color(ttfont, ot_paint.Color.PaletteIndex, ot_paint.Color.Alpha)
    _apply_solid_paint(svg_path, PaintSolid(color))


def _apply_gradient_ot_paint(
    svg_defs: etree.Element,
    svg_path: etree.Element,
    ttfont: ttLib.TTFont,
    font_to_vbox: Affine2D,
    ot_paint: otTables.Paint,
    transform: Affine2D = Affine2D.identity(),
):
    paint = _gradient_paint(ttfont, ot_paint)
    # For radial gradients we want to keep cirlces as such, so we must decompose into
    # a uniform scale+translate plus a remainder to encode as gradientTransform.
    # Whereas for linear gradients, we can simply apply the whole combined transform to
    # start/end points and omit gradientTransform attribute.
    coord_transform = Affine2D.compose_ltr((transform, font_to_vbox))
    remaining_transform = Affine2D.identity()
    if paint.format == PaintRadialGradient.format:
        coord_transform, remaining_transform = color_glyph._decompose_uniform_transform(
            coord_transform
        )
    paint = _map_gradient_coordinates(paint, coord_transform)
    _apply_gradient_paint(svg_defs, svg_path, paint, transform=remaining_transform)


def _colr_v0_glyph_to_svg(
    ttfont: ttLib.TTFont,
    glyph_set: ttLib.ttFont._TTGlyphSet,
    view_box: Rect,
    glyph_name: str,
) -> etree.Element:
    svg_root = _svg_root(view_box)
    ascender = ttfont["OS/2"].sTypoAscender
    descender = ttfont["OS/2"].sTypoDescender
    width = ttfont["hmtx"][glyph_name][0]
    font_to_vbox = _map_font_space_to_viewbox(view_box, ascender, descender, width)

    for glyph_layer in ttfont["COLR"].ColorLayers[glyph_name]:
        svg_path = etree.SubElement(svg_root, "path")
        paint = PaintSolid(_color(ttfont, glyph_layer.colorID))
        _apply_solid_paint(svg_path, paint)
        _draw_svg_path(svg_path, glyph_set, glyph_layer.name, font_to_vbox)

    return svg_root


def _colr_v1_paint_to_svg(
    ttfont: ttLib.TTFont,
    glyph_set: Mapping[str, Any],
    svg_root: etree.Element,
    font_to_vbox: Affine2D,
    ot_paint: otTables.Paint,
    svg_path: Optional[etree.Element] = None,
    transform: Affine2D = Affine2D.identity(),
):
    if ot_paint.Format == PaintSolid.format:
        assert svg_path is not None
        _apply_solid_ot_paint(svg_path, ttfont, ot_paint)
    elif ot_paint.Format in _GRADIENT_PAINT_FORMATS:
        assert svg_path is not None
        svg_defs = svg_root[0]
        _apply_gradient_ot_paint(
            svg_defs, svg_path, ttfont, font_to_vbox, ot_paint, transform
        )
    elif ot_paint.Format == PaintGlyph.format:
        assert svg_path is None, "recursive PaintGlyph is unsupported"
        layer_glyph = ot_paint.Glyph
        svg_path = etree.SubElement(svg_root, "path")
        if transform != Affine2D.identity():
            svg_path.attrib["transform"] = _svg_matrix(transform)

        _colr_v1_paint_to_svg(
            ttfont,
            glyph_set,
            svg_root,
            font_to_vbox,
            ot_paint.Paint,
            svg_path,
        )

        _draw_svg_path(svg_path, glyph_set, layer_glyph, font_to_vbox)
    elif ot_paint.Format == PaintTransform.format:
        transform = Affine2D.product(
            (
                Affine2D.identity()
                if not ot_paint.Transform
                else Affine2D(
                    ot_paint.Transform.xx,
                    ot_paint.Transform.yx,
                    ot_paint.Transform.xy,
                    ot_paint.Transform.yy,
                    ot_paint.Transform.dx,
                    ot_paint.Transform.dy,
                )
            ),
            transform,
        )
        _colr_v1_paint_to_svg(
            ttfont,
            glyph_set,
            svg_root,
            font_to_vbox,
            ot_paint.Paint,
            svg_path,
            transform=transform,
        )
    elif ot_paint.Format == PaintColrLayers.format:
        layerList = ttfont["COLR"].table.LayerV1List.Paint
        assert layerList, "Paint layers without a layer list :("
        for child_paint in layerList[
            ot_paint.FirstLayerIndex : ot_paint.FirstLayerIndex + ot_paint.NumLayers
        ]:
            _colr_v1_paint_to_svg(
                ttfont,
                glyph_set,
                svg_root,
                font_to_vbox,
                child_paint,
                svg_path,
                transform=transform,
            )
    else:
        raise NotImplementedError(ot_paint.Format)


def _colr_v1_glyph_to_svg(
    ttfont: ttLib.TTFont,
    glyph_set: ttLib.ttFont._TTGlyphSet,
    view_box: Rect,
    glyph: otTables.BaseGlyphRecord,
) -> etree.Element:
    glyph_set = ttfont.getGlyphSet()
    svg_root = _svg_root(view_box)
    ascender = ttfont["OS/2"].sTypoAscender
    descender = ttfont["OS/2"].sTypoDescender
    width = ttfont["hmtx"][glyph.BaseGlyph][0]
    font_to_vbox = _map_font_space_to_viewbox(view_box, ascender, descender, width)
    _colr_v1_paint_to_svg(ttfont, glyph_set, svg_root, font_to_vbox, glyph.Paint)
    return svg_root


def _colr_v0_to_svgs(view_box: Rect, ttfont: ttLib.TTFont) -> Dict[str, SVG]:
    glyph_set = ttfont.getGlyphSet()
    return {
        g: SVG.fromstring(
            etree.tostring(_colr_v0_glyph_to_svg(ttfont, glyph_set, view_box, g))
        )
        for g in ttfont["COLR"].ColorLayers
    }


def _colr_v1_to_svgs(view_box: Rect, ttfont: ttLib.TTFont) -> Dict[str, SVG]:
    glyph_set = ttfont.getGlyphSet()
    return {
        g.BaseGlyph: SVG.fromstring(
            etree.tostring(_colr_v1_glyph_to_svg(ttfont, glyph_set, view_box, g))
        )
        for g in ttfont["COLR"].table.BaseGlyphV1List.BaseGlyphV1Record
    }


def colr_to_svg(view_box: Rect, ttfont: ttLib.TTFont) -> Dict[str, SVG]:
    """For testing only, don't use for real!"""
    assert len(ttfont["CPAL"].palettes) == 1, "We assume one palette"

    if ttfont["COLR"].version == 0:
        return _colr_v0_to_svgs(view_box, ttfont)
    return _colr_v1_to_svgs(view_box, ttfont)
