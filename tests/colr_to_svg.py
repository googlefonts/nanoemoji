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
from nanoemoji.glyph_reuse import GlyphReuseCache
from nanoemoji.paint import (
    ColorStop,
    CompositeMode,
    Extend,
    Paint,
    PaintSolid,
    PaintLinearGradient,
    PaintRadialGradient,
    PaintGlyph,
    PaintColrGlyph,
    PaintComposite,
    PaintColrLayers,
    is_transform,
    _decompose_uniform_transform,
)
from nanoemoji.svg import (
    _svg_matrix,
    _apply_solid_paint,
    _apply_gradient_paint,
    _map_gradient_coordinates,
    _GradientPaint,
    ReuseCache,
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
    stops = tuple(
        ColorStop(
            stop.StopOffset,
            _color(ttfont, stop.PaletteIndex, stop.Alpha),
        )
        for stop in ot_paint.ColorLine.ColorStop
    )
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
    color = _color(ttfont, ot_paint.PaletteIndex, ot_paint.Alpha)
    _apply_solid_paint(svg_path, PaintSolid(color))


def _apply_gradient_ot_paint(
    svg_defs: etree.Element,
    svg_path: etree.Element,
    ttfont: ttLib.TTFont,
    font_to_vbox: Affine2D,
    ot_paint: otTables.Paint,
    reuse_cache: ReuseCache,
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
        coord_transform, remaining_transform = _decompose_uniform_transform(
            coord_transform
        )
    paint = _map_gradient_coordinates(paint, coord_transform)
    _apply_gradient_paint(
        svg_defs, svg_path, paint, reuse_cache, transform=remaining_transform
    )


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
    parent_el: etree.Element,
    svg_defs: etree.Element,
    font_to_vbox: Affine2D,
    ot_paint: otTables.Paint,
    reuse_cache: ReuseCache,
    transform: Affine2D = Affine2D.identity(),
):
    def descend(parent: etree.Element, paint: otTables.Paint):
        _colr_v1_paint_to_svg(
            ttfont,
            glyph_set,
            parent,
            svg_defs,
            font_to_vbox,
            paint,
            reuse_cache,
            transform=transform,
        )

    if ot_paint.Format == PaintSolid.format:
        _apply_solid_ot_paint(parent_el, ttfont, ot_paint)
    elif ot_paint.Format in _GRADIENT_PAINT_FORMATS:
        _apply_gradient_ot_paint(
            svg_defs, parent_el, ttfont, font_to_vbox, ot_paint, reuse_cache, transform
        )
    elif ot_paint.Format == PaintGlyph.format:
        layer_glyph = ot_paint.Glyph
        svg_path = etree.SubElement(parent_el, "path")

        # This only occurs if path is reused; we could wire up use. But for now ... not.
        if transform != Affine2D.identity():
            svg_transform = Affine2D.compose_ltr(
                (font_to_vbox.inverse(), transform, font_to_vbox)
            )
            svg_path.attrib["transform"] = _svg_matrix(svg_transform)
            # we must reset the current user space when setting the 'transform'
            # attribute on a <path>, since that already affects the gradients used
            # and we don't want the transform to be applied twice to gradients:
            # https://github.com/googlefonts/nanoemoji/issues/334
            transform = Affine2D.identity()

        descend(svg_path, ot_paint.Paint)

        _draw_svg_path(svg_path, glyph_set, layer_glyph, font_to_vbox)
    elif is_transform(ot_paint.Format):
        paint = Paint.from_ot(ot_paint)
        transform @= paint.gettransform()
        descend(parent_el, ot_paint.Paint)
    elif ot_paint.Format == PaintColrLayers.format:
        layerList = ttfont["COLR"].table.LayerList.Paint
        assert layerList, "Paint layers without a layer list :("
        for child_paint in layerList[
            ot_paint.FirstLayerIndex : ot_paint.FirstLayerIndex + ot_paint.NumLayers
        ]:
            descend(parent_el, child_paint)

    elif ot_paint.Format == PaintComposite.format and (
        ot_paint.CompositeMode == CompositeMode.SRC_IN
        and ot_paint.BackdropPaint.Format == PaintSolid.format
    ):
        # Only simple group opacity for now
        color = _color(
            ttfont,
            ot_paint.BackdropPaint.PaletteIndex,
            ot_paint.BackdropPaint.Alpha,
        )
        if color[:3] != (0, 0, 0):
            raise NotImplementedError(color)
        g = etree.SubElement(parent_el, "g")
        g.attrib["opacity"] = ntos(color.alpha)
        descend(g, ot_paint.SourcePaint)

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
    svg_defs = svg_root[0]
    ascender = ttfont["OS/2"].sTypoAscender
    descender = ttfont["OS/2"].sTypoDescender
    width = ttfont["hmtx"][glyph.BaseGlyph][0]
    font_to_vbox = _map_font_space_to_viewbox(view_box, ascender, descender, width)
    reuse_cache = _new_reuse_cache()
    _colr_v1_paint_to_svg(
        ttfont, glyph_set, svg_root, svg_defs, font_to_vbox, glyph.Paint, reuse_cache
    )
    return svg_root


def _new_reuse_cache() -> ReuseCache:
    return ReuseCache(0.1, GlyphReuseCache(0.1))


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
        for g in ttfont["COLR"].table.BaseGlyphList.BaseGlyphPaintRecord
    }


def colr_to_svg(
    view_box: Rect,
    ttfont: ttLib.TTFont,
    rounding_ndigits: Optional[int] = None,
) -> Dict[str, SVG]:
    """For testing only, don't use for real!"""
    assert len(ttfont["CPAL"].palettes) == 1, "We assume one palette"

    colr_version = ttfont["COLR"].version
    if colr_version == 0:
        svgs = _colr_v0_to_svgs(view_box, ttfont)
    elif colr_version == 1:
        svgs = _colr_v1_to_svgs(view_box, ttfont)
    else:
        raise NotImplementedError(colr_version)

    if rounding_ndigits is None:
        return svgs
    return {g: svg.round_floats(rounding_ndigits) for g, svg in svgs.items()}
