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
from picosvg import svg_meta
from picosvg.svg import SVG
from fontTools import ttLib
from picosvg.geometric_types import Rect
import test_helper
from lxml import etree
from typing import Tuple
from fontTools.pens import svgPathPen
from fontTools.pens import transformPen
from fontTools.ttLib.tables import otTables


_PAINT_SOLID = 1
_PAINT_LINEAR_GRADIENT = 2
_PAINT_RADIAL_GRADIENT = 3


def _emsquare_to_viewbox(upem: int, view_box: Rect):
    if view_box != Rect(0, 0, view_box.w, view_box.w):
        raise ValueError("We simply must have a SQUARE from 0,0")
    return color_glyph.map_viewbox_to_font_emsquare(Rect(0, 0, upem, upem), view_box.w)


def _svg_root(view_box: Rect) -> etree.Element:
    svg_tree = etree.parse(test_helper.locate_test_file("colr_to_svg_template.svg"))
    svg_root = svg_tree.getroot()
    svg_root.attrib["viewBox"] = f"{view_box.x} {view_box.y} {view_box.w} {view_box.h}"
    return svg_root


def _nice_path(svg_pen: svgPathPen.SVGPathPen) -> str:
    # svgPathPen doesn't format #s nicely
    commands = []
    for command in svg_pen._commands:
        parts = (command[0],)
        if len(command) > 1:
            parts += tuple(float(v) for v in command[1:].split(" "))
        commands.append(svg_meta.path_segment(*parts))
    return " ".join(commands)


def _draw_svg_path(
    svg_path: etree.Element, view_box: Rect, ttfont: ttLib.TTFont, glyph_name: str
):
    svg_pen = svgPathPen.SVGPathPen(None)

    upem_to_vbox = _emsquare_to_viewbox(ttfont["head"].unitsPerEm, view_box)
    transform_pen = transformPen.TransformPen(svg_pen, upem_to_vbox)

    glyph = ttfont["glyf"][glyph_name]
    glyph.draw(transform_pen, ttfont["glyf"])

    svg_path.attrib["d"] = _nice_path(svg_pen)


def _solid_paint(
    svg_path: etree.Element, ttfont: ttLib.TTFont, palette_index: int, alpha: float
):
    color = ttfont["CPAL"].palettes[0][palette_index]
    named_color = colors.color_name((color.red, color.green, color.blue))
    if named_color:
        svg_path.attrib["fill"] = named_color
    else:
        svg_path.attrib["fill"] = f"#{color.red:02x}{color.green:02x}{color.blue:02x}"

    if alpha is None:
        alpha = color.alpha / 255
    else:
        assert color.alpha == 255

    if alpha != 1.0:
        svg_path.attrib["opacity"] = svg_meta.ntos(alpha)


def _colr_v0_glyph_to_svg(
    ttfont: ttLib.TTFont, view_box: Rect, glyph_name: str
) -> etree.Element:

    svg_root = _svg_root(view_box)

    for glyph_layer in ttfont["COLR"].ColorLayers[glyph_name]:
        svg_path = etree.SubElement(svg_root, "path")
        _solid_paint(svg_path, ttfont, glyph_layer.colorID, None)
        _draw_svg_path(svg_path, view_box, ttfont, glyph_layer.name)

    return svg_root


def _colr_v1_glyph_to_svg(
    ttfont: ttLib.TTFont, view_box: Rect, glyph: otTables.BaseGlyphRecord
) -> etree.Element:

    svg_root = _svg_root(view_box)
    cpal_colors = ttfont["CPAL"].palettes[0]
    for glyph_layer in glyph.LayerV1Array.LayerV1Record:
        svg_path = etree.SubElement(svg_root, "path")

        # TODO care about variations, such as for transparency
        paint = glyph_layer.Paint
        if paint.Format == _PAINT_SOLID:
            _solid_paint(
                svg_path,
                ttfont,
                paint.Color.PaletteIndex,
                1 - paint.Color.Transparency.value,
            )
        elif paint.Format == _PAINT_LINEAR_GRADIENT:
            raise ValueError("linear gradient paint not supported")
        elif paint.Format == _PAINT_RADIAL_GRADIENT:
            raise ValueError("radial gradient paint not supported")

        _draw_svg_path(svg_path, view_box, ttfont, glyph_layer.LayerGlyph)

    return svg_root


def _colr_v0_to_svgs(view_box: Rect, ttfont: ttLib.TTFont) -> Tuple[SVG]:
    return tuple(
        SVG.fromstring(etree.tostring(_colr_v0_glyph_to_svg(ttfont, view_box, g)))
        for g in ttfont["COLR"].ColorLayers
    )


def _colr_v1_to_svgs(view_box: Rect, ttfont: ttLib.TTFont) -> Tuple[SVG]:
    # TODO: COLRv1: Gradient definitions
    return tuple(
        SVG.fromstring(etree.tostring(_colr_v1_glyph_to_svg(ttfont, view_box, g)))
        for g in ttfont["COLR"].table.BaseGlyphV1Array.BaseGlyphV1Record
    )


def colr_to_svg(view_box: Rect, ttfont: ttLib.TTFont) -> Tuple[SVG]:
    """For testing only, don't use for real!"""
    assert len(ttfont["CPAL"].palettes) == 1, "We assume one palette"

    # getattr: COLRv1 'table_C_O_L_R_' object has no attribute 'version'
    if getattr(ttfont["COLR"], "version", 1) == 0:
        return _colr_v0_to_svgs(view_box, ttfont)
    return _colr_v1_to_svgs(view_box, ttfont)
