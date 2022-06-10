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

from absl import logging
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
from nanoemoji.util import only
from picosvg.svg import SVG
from picosvg.svg_meta import ntos
from picosvg.svg_transform import Affine2D
from fontTools import ttLib
from picosvg.geometric_types import Point, Rect
from lxml import etree
from typing import Any, Callable, Dict, Iterable, Mapping, Optional, Tuple
from fontTools.pens import transformPen
from fontTools.ttLib.tables import otTables


_FOREGROUND_COLOR_INDEX = 0xFFFF
_GRADIENT_PAINT_FORMATS = (PaintLinearGradient.format, PaintRadialGradient.format)
_COLR_TO_SVG_TEMPLATE = r'<svg viewBox="TBD" xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink"><defs/></svg>'

ViewboxCallback = Callable[[str], Rect]  # f(glyph_name) -> Rect


def map_font_space_to_viewbox(view_box: Rect, glyph_region: Rect) -> Affine2D:
    # SVG, as some of us are very fond of forgetting, has +y going down
    assert glyph_region.y <= 0
    ascender = -glyph_region.y
    descender = -(glyph_region.h - ascender)
    assert descender <= 0
    width = glyph_region.w

    return color_glyph.map_viewbox_to_font_space(
        view_box, ascender, descender, width, Affine2D.identity()
    ).inverse()


def _svg_root(view_box: Rect) -> etree.Element:
    svg_root = etree.fromstring(_COLR_TO_SVG_TEMPLATE)
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
    palette = ttfont["CPAL"].palettes[0]
    if palette_index == _FOREGROUND_COLOR_INDEX:
        return colors.Color.fromstring("black")  # as good a guess as any
    if palette_index >= len(palette):
        raise IndexError(f"{palette_index} illegal in palette of {len(palette)}")
    cpal_color = palette[palette_index]
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
    view_box_callback: ViewboxCallback,
    glyph_name: str,
) -> etree.Element:
    view_box, font_to_vbox = _view_box_and_transform(
        ttfont, view_box_callback, glyph_name
    )
    svg_root = _svg_root(view_box)
    for glyph_layer in ttfont["COLR"].ColorLayers[glyph_name]:
        svg_path = etree.SubElement(svg_root, "path")
        paint = PaintSolid(_color(ttfont, glyph_layer.colorID))
        _apply_solid_paint(svg_path, paint)
        _draw_svg_path(svg_path, glyph_set, glyph_layer.name, font_to_vbox)

    return svg_root


def _apply_transform(
    transform: Affine2D, font_to_vbox: Affine2D, el: etree.Element
) -> Affine2D:
    if transform == Affine2D.identity():
        return Affine2D.identity()

    svg_transform = Affine2D.compose_ltr(
        (font_to_vbox.inverse(), transform, font_to_vbox)
    )
    el.attrib["transform"] = _svg_matrix(svg_transform)
    # we must reset the current user space when setting the 'transform'
    # attribute on a <path>, since that already affects the gradients used
    # and we don't want the transform to be applied twice to gradients:
    # https://github.com/googlefonts/nanoemoji/issues/334
    return Affine2D.identity()


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

        # Transform only occurs with reuse; we could wire up use. But for now ... not.
        transform = _apply_transform(transform, font_to_vbox, svg_path)

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

    elif ot_paint.Format == PaintComposite.format:
        if (
            ot_paint.CompositeMode == CompositeMode.SRC_IN
            and ot_paint.BackdropPaint.Format == PaintSolid.format
        ):
            # Special-case simple PaintComposite for group opacity
            color = _color(
                ttfont,
                ot_paint.BackdropPaint.PaletteIndex,
                ot_paint.BackdropPaint.Alpha,
            )
            if color[:3] == (0, 0, 0):
                g = etree.SubElement(parent_el, "g")
                g.attrib["opacity"] = ntos(color.alpha)
                descend(g, ot_paint.SourcePaint)
                return

        # https://github.com/googlefonts/nanoemoji/issues/409
        logging.warning(
            "PaintComposite => SVG not supported at the moment; "
            "only BackdropPaint is kept."
        )
        descend(parent_el, ot_paint.BackdropPaint)

    elif ot_paint.Format == PaintColrGlyph.format:
        el = parent_el
        if transform != Affine2D.identity():
            el = etree.SubElement(parent_el, "g")
            # Transform only occurs with reuse; we could wire up use. But for now ... not.
            transform = _apply_transform(transform, font_to_vbox, el)
        base_rec = only(
            r
            for r in ttfont["COLR"].table.BaseGlyphList.BaseGlyphPaintRecord
            if r.BaseGlyph == ot_paint.Glyph
        )
        descend(el, base_rec.Paint)

    else:
        raise NotImplementedError(ot_paint.Format)


def glyph_region(ttfont: ttLib.TTFont, glyph_name: str) -> Rect:
    """The area occupied by the glyph, NOT factoring in that Y flips.

    map_font_space_to_viewbox handles font +y goes up => svg +y goes down."""
    width = ttfont["hmtx"][glyph_name][0]
    if width == 0:
        width = ttfont["glyf"][glyph_name].xMax
    return Rect(
        0,
        -ttfont["OS/2"].sTypoAscender,
        width,
        ttfont["OS/2"].sTypoAscender - ttfont["OS/2"].sTypoDescender,
    )


def _view_box_and_transform(
    ttfont: ttLib.TTFont, view_box_callback: ViewboxCallback, glyph_name: str
) -> Tuple[Rect, Affine2D]:

    view_box = view_box_callback(glyph_name)
    assert view_box.w > 0, f"0-width viewBox for {glyph_name}?!"

    region = glyph_region(ttfont, glyph_name)
    assert region.w > 0, f"0-width region for {glyph_name}?!"

    font_to_vbox = map_font_space_to_viewbox(view_box, region)

    return (view_box, font_to_vbox)


def _colr_v1_glyph_to_svg(
    ttfont: ttLib.TTFont,
    glyph_set: ttLib.ttFont._TTGlyphSet,
    view_box_callback: ViewboxCallback,
    glyph: otTables.BaseGlyphRecord,
) -> etree.Element:
    view_box, font_to_vbox = _view_box_and_transform(
        ttfont, view_box_callback, glyph.BaseGlyph
    )
    svg_root = _svg_root(view_box)
    svg_defs = svg_root[0]

    reuse_cache = _new_reuse_cache()
    glyph_set = ttfont.getGlyphSet()
    _colr_v1_paint_to_svg(
        ttfont, glyph_set, svg_root, svg_defs, font_to_vbox, glyph.Paint, reuse_cache
    )
    return svg_root


def _new_reuse_cache() -> ReuseCache:
    return ReuseCache(0.1, GlyphReuseCache(0.1))


def colr_glyphs(font: ttLib.TTFont) -> Iterable[int]:
    colr = font["COLR"]
    if colr.version == 0:
        for glyph_name in colr.ColorLayers:
            yield font.getGlyphID(glyph_name)
    else:
        assert colr.version == 1
        assert not getattr(colr, "ColorLayers", ()), "TODO: mixed v0/v1 support"
        for base_glyph in font["COLR"].table.BaseGlyphList.BaseGlyphPaintRecord:
            yield font.getGlyphID(base_glyph.BaseGlyph)


def _colr_v0_to_svgs(
    view_box_callback: ViewboxCallback, ttfont: ttLib.TTFont
) -> Dict[str, SVG]:
    glyph_set = ttfont.getGlyphSet()
    return {
        g: SVG.fromstring(
            etree.tostring(
                _colr_v0_glyph_to_svg(ttfont, glyph_set, view_box_callback, g)
            )
        )
        for g in ttfont["COLR"].ColorLayers
    }


def _colr_v1_to_svgs(
    view_box_callback: ViewboxCallback, ttfont: ttLib.TTFont
) -> Dict[str, SVG]:
    glyph_set = ttfont.getGlyphSet()
    return {
        g.BaseGlyph: SVG.fromstring(
            etree.tostring(
                _colr_v1_glyph_to_svg(ttfont, glyph_set, view_box_callback, g)
            )
        )
        for g in ttfont["COLR"].table.BaseGlyphList.BaseGlyphPaintRecord
    }


def colr_to_svg(
    view_box_callback: ViewboxCallback,
    ttfont: ttLib.TTFont,
    rounding_ndigits: Optional[int] = None,
) -> Dict[str, SVG]:
    """For testing only, don't use for real!"""
    assert len(ttfont["CPAL"].palettes) == 1, "We assume one palette"

    colr_version = ttfont["COLR"].version
    if colr_version == 0:
        svgs = _colr_v0_to_svgs(view_box_callback, ttfont)
    elif colr_version == 1:
        svgs = _colr_v1_to_svgs(view_box_callback, ttfont)
    else:
        raise NotImplementedError(colr_version)

    if rounding_ndigits is None:
        return svgs
    return {g: svg.round_floats(rounding_ndigits) for g, svg in svgs.items()}
