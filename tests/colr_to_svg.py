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
from nanoemoji.paint import Extend
from nanoemoji.svg import _svg_matrix, _ntos
from nanoemoji.svg_path import SVGPathPen
from picosvg import svg_meta
from picosvg.svg import SVG
from picosvg.svg_transform import Affine2D
from fontTools import ttLib
from picosvg.geometric_types import Point, Rect
import test_helper
from lxml import etree
from typing import Dict, NamedTuple, Sequence
from fontTools.pens import transformPen
from fontTools.ttLib.tables import otTables

_PAINT_SOLID = 1
_PAINT_LINEAR_GRADIENT = 2
_PAINT_RADIAL_GRADIENT = 3


class _ColorStop(NamedTuple):
    offset: float
    palette_index: int
    alpha: float


def _emsquare_to_viewbox(upem: int, view_box: Rect):
    if view_box != Rect(0, 0, view_box.w, view_box.w):
        raise ValueError("We simply must have a SQUARE from 0,0")
    return color_glyph.map_viewbox_to_font_emsquare(Rect(0, 0, upem, upem), view_box.w)


def _svg_root(view_box: Rect) -> etree.Element:
    svg_tree = etree.parse(test_helper.locate_test_file("colr_to_svg_template.svg"))
    svg_root = svg_tree.getroot()
    svg_root.attrib["viewBox"] = f"{view_box.x} {view_box.y} {view_box.w} {view_box.h}"
    return svg_root


def _draw_svg_path(
    svg_path: etree.Element,
    view_box: Rect,
    ttfont: ttLib.TTFont,
    glyph_name: str,
    glyph_set: ttLib.ttFont._TTGlyphSet,
):
    # use glyph set to resolve references in composite glyphs
    svg_pen = SVGPathPen(glyph_set)
    # wrap svg pen with "filter" pen mapping coordinates from UPEM to SVG space
    upem_to_vbox = _emsquare_to_viewbox(ttfont["head"].unitsPerEm, view_box)
    transform_pen = transformPen.TransformPen(svg_pen, upem_to_vbox)

    glyph = glyph_set[glyph_name]
    glyph.draw(transform_pen)

    svg_path.attrib["d"] = svg_pen.path.d


def _svg_color_and_opacity(color, alpha=1.0):
    named_color = colors.color_name((color.red, color.green, color.blue))
    if named_color:
        svg_color = named_color
    else:
        svg_color = f"#{color.red:02x}{color.green:02x}{color.blue:02x}"

    alpha *= color.alpha / 255

    if alpha != 1.0:
        svg_opacity = _ntos(alpha)
    else:
        svg_opacity = None

    return svg_color, svg_opacity


def _solid_paint(
    svg_path: etree.Element,
    ttfont: ttLib.TTFont,
    palette_index: int,
    alpha: float = 1.0,
):
    color = ttfont["CPAL"].palettes[0][palette_index]
    svg_color, svg_opacity = _svg_color_and_opacity(color, alpha)
    svg_path.attrib["fill"] = svg_color
    if svg_opacity:
        svg_path.attrib["opacity"] = svg_opacity


def _linear_gradient_paint(
    svg_defs: etree.Element,
    svg_path: etree.Element,
    ttfont: ttLib.TTFont,
    view_box: Rect,
    stops: Sequence[_ColorStop],
    extend: Extend,
    p0: Point,
    p1: Point,
    p2: Point,
):
    # P2 allows to rotate the linear gradient independently of the end points P0 and P1.
    # Below we compute P3 which is the projection of P1 onto the line between P0 and P2
    # (aka the "normal" line, perpendicular to the linear gradient "front"). The vector
    # P3-P0 is the "effective" linear gradient vector after this rotation.
    # When P2 is collinear with P0 and P1, then P3 (projection of P1 onto the normal) is
    # == P1 itself thus there's no rotation. When P2 sits on a line passing by P0 and
    # perpendicular to the P1-P0 gradient vector, then this projected P3 == P0 and the
    # gradient degenerates to a solid paint (the last color stop).
    # NOTE: in nanoemoji-built fonts, this point P3 is always == P2, so we could just
    # use that here, but the spec does not mandate that P2 be on the "front" line
    # that passes by P1, it can be anywhere, hence we compute P3.
    p3 = p0 + (p1 - p0).projection(p2 - p0)

    upem_to_vbox = _emsquare_to_viewbox(ttfont["head"].unitsPerEm, view_box)
    x1, y1 = upem_to_vbox.map_point(p0)
    x2, y2 = upem_to_vbox.map_point(p3)

    gradient = etree.SubElement(svg_defs, "linearGradient")
    gradient_id = gradient.attrib["id"] = f"g{len(svg_defs)}"
    gradient.attrib["gradientUnits"] = "userSpaceOnUse"
    gradient.attrib["x1"] = _ntos(x1)
    gradient.attrib["y1"] = _ntos(y1)
    gradient.attrib["x2"] = _ntos(x2)
    gradient.attrib["y2"] = _ntos(y2)
    if extend != Extend.PAD:
        gradient.attrib["spreadMethod"] = extend.name.lower()

    palette = ttfont["CPAL"].palettes[0]
    for stop in stops:
        stop_el = etree.SubElement(gradient, "stop")
        stop_el.attrib["offset"] = _ntos(stop.offset)
        cpal_color = palette[stop.palette_index]
        svg_color, svg_opacity = _svg_color_and_opacity(cpal_color, stop.alpha)
        stop_el.attrib["stop-color"] = svg_color
        if svg_opacity:
            stop_el.attrib["stop-opacity"] = svg_opacity

    svg_path.attrib["fill"] = f"url(#{gradient_id})"


def _radial_gradient_paint(
    svg_defs: etree.Element,
    svg_path: etree.Element,
    ttfont: ttLib.TTFont,
    view_box: Rect,
    stops: Sequence[_ColorStop],
    extend: Extend,
    c0: Point,
    c1: Point,
    r0: int,
    r1: int,
    transform: Affine2D,
):
    # map centres and radii from UPEM to SVG space
    upem_to_vbox = _emsquare_to_viewbox(ttfont["head"].unitsPerEm, view_box)
    c0 = upem_to_vbox.map_point(c0)
    c1 = upem_to_vbox.map_point(c1)
    # _emsquare_to_viewbox guarantees view_box is square so scaling radii is ok
    r0 = upem_to_vbox.map_point((r0, 0)).x
    r1 = upem_to_vbox.map_point((r1, 0)).x

    # COLRv1 centre points aren't affected by the gradient Affine2x2, whereas in SVG
    # gradientTransform applies to everything; to prevent that, we must also map
    # the centres with the inverse of gradientTransform, so they won't move.
    inverse_transform = transform.inverse()
    fx, fy = inverse_transform.map_point(c0)
    cx, cy = inverse_transform.map_point(c1)

    gradient = etree.SubElement(svg_defs, "radialGradient")
    gradient_id = gradient.attrib["id"] = f"g{len(svg_defs)}"
    gradient.attrib["gradientUnits"] = "userSpaceOnUse"
    gradient.attrib["fx"] = _ntos(fx)
    gradient.attrib["fy"] = _ntos(fy)
    gradient.attrib["fr"] = _ntos(r0)
    gradient.attrib["cx"] = _ntos(cx)
    gradient.attrib["cy"] = _ntos(cy)
    gradient.attrib["r"] = _ntos(r1)
    if transform != Affine2D.identity():
        gradient.attrib["gradientTransform"] = _svg_matrix(transform)
    if extend != Extend.PAD:
        gradient.attrib["spreadMethod"] = extend.name.lower()

    palette = ttfont["CPAL"].palettes[0]
    for stop in stops:
        stop_el = etree.SubElement(gradient, "stop")
        stop_el.attrib["offset"] = _ntos(stop.offset)
        cpal_color = palette[stop.palette_index]
        svg_color, svg_opacity = _svg_color_and_opacity(cpal_color, stop.alpha)
        stop_el.attrib["stop-color"] = svg_color
        if svg_opacity:
            stop_el.attrib["stop-opacity"] = svg_opacity

    svg_path.attrib["fill"] = f"url(#{gradient_id})"


def _colr_v0_glyph_to_svg(
    ttfont: ttLib.TTFont, view_box: Rect, glyph_name: str
) -> etree.Element:

    svg_root = _svg_root(view_box)

    glyph_set = ttfont.getGlyphSet()
    for glyph_layer in ttfont["COLR"].ColorLayers[glyph_name]:
        svg_path = etree.SubElement(svg_root, "path")
        _solid_paint(svg_path, ttfont, glyph_layer.colorID)
        _draw_svg_path(svg_path, view_box, ttfont, glyph_layer.name, glyph_set)

    return svg_root


def _colr_v1_glyph_to_svg(
    ttfont: ttLib.TTFont, view_box: Rect, glyph: otTables.BaseGlyphRecord
) -> etree.Element:
    glyph_set = ttfont.getGlyphSet()
    svg_root = _svg_root(view_box)
    defs = svg_root[0]
    for glyph_layer in glyph.LayerV1List.LayerV1Record:
        svg_path = etree.SubElement(svg_root, "path")

        # TODO care about variations, such as for alpha
        paint = glyph_layer.Paint
        if paint.Format == _PAINT_SOLID:
            _solid_paint(
                svg_path, ttfont, paint.Color.PaletteIndex, paint.Color.Alpha.value
            )
        elif paint.Format == _PAINT_LINEAR_GRADIENT:
            _linear_gradient_paint(
                defs,
                svg_path,
                ttfont,
                view_box,
                stops=[
                    _ColorStop(
                        stop.StopOffset.value,
                        stop.Color.PaletteIndex,
                        stop.Color.Alpha.value,
                    )
                    for stop in paint.ColorLine.ColorStop
                ],
                extend=Extend((paint.ColorLine.Extend.value,)),
                p0=Point(paint.x0.value, paint.y0.value),
                p1=Point(paint.x1.value, paint.y1.value),
                p2=Point(paint.x2.value, paint.y2.value),
            )
        elif paint.Format == _PAINT_RADIAL_GRADIENT:
            _radial_gradient_paint(
                defs,
                svg_path,
                ttfont,
                view_box,
                stops=[
                    _ColorStop(
                        stop.StopOffset.value,
                        stop.Color.PaletteIndex,
                        stop.Color.Alpha.value,
                    )
                    for stop in paint.ColorLine.ColorStop
                ],
                extend=Extend((paint.ColorLine.Extend.value,)),
                c0=Point(paint.x0.value, paint.y0.value),
                c1=Point(paint.x1.value, paint.y1.value),
                r0=paint.r0.value,
                r1=paint.r1.value,
                transform=(
                    Affine2D.identity()
                    if not paint.Transform
                    else Affine2D(
                        paint.Transform.xx.value,
                        paint.Transform.xy.value,
                        paint.Transform.yx.value,
                        paint.Transform.yy.value,
                        0,
                        0,
                    )
                ),
            )

        _draw_svg_path(svg_path, view_box, ttfont, glyph_layer.LayerGlyph, glyph_set)

    return svg_root


def _colr_v0_to_svgs(view_box: Rect, ttfont: ttLib.TTFont) -> Dict[str, SVG]:
    return {
        g: SVG.fromstring(etree.tostring(_colr_v0_glyph_to_svg(ttfont, view_box, g)))
        for g in ttfont["COLR"].ColorLayers
    }


def _colr_v1_to_svgs(view_box: Rect, ttfont: ttLib.TTFont) -> Dict[str, SVG]:
    return {
        g.BaseGlyph: SVG.fromstring(
            etree.tostring(_colr_v1_glyph_to_svg(ttfont, view_box, g))
        )
        for g in ttfont["COLR"].table.BaseGlyphV1List.BaseGlyphV1Record
    }


def colr_to_svg(view_box: Rect, ttfont: ttLib.TTFont) -> Dict[str, SVG]:
    """For testing only, don't use for real!"""
    assert len(ttfont["CPAL"].palettes) == 1, "We assume one palette"

    if ttfont["COLR"].version == 0:
        return _colr_v0_to_svgs(view_box, ttfont)
    return _colr_v1_to_svgs(view_box, ttfont)
