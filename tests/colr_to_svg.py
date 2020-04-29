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


def _emsquare_to_viewbox(upem: int, view_box: Rect):
    if view_box != Rect(0, 0, view_box.w, view_box.w):
        raise ValueError("We simply must have a BOX from 0,0")
    return color_glyph.map_viewbox_to_emsquare(Rect(0, 0, upem, upem), view_box.w)


def _svg_root(view_box: Rect) -> etree.Element:
    svg_tree = etree.parse(test_helper.locate_test_file("colr_to_svg_template.svg"))
    svg_root = svg_tree.getroot()
    svg_root.attrib["viewBox"] = f"{view_box.x} {view_box.y} {view_box.w} {view_box.h}"
    return svg_root


def _colr_v0_to_svg(
    ttfont: ttLib.TTFont, view_box: Rect, glyph_name: str
) -> etree.Element:
    cpal_colors = ttfont["CPAL"].palettes[0]
    svg_root = _svg_root(view_box)

    # Coordinate scaling
    affine = _emsquare_to_viewbox(ttfont["head"].unitsPerEm, view_box)

    for glyph_layer in ttfont["COLR"].ColorLayers[glyph_name]:
        svg_path = etree.SubElement(svg_root, "path")
        color = cpal_colors[glyph_layer.colorID]
        named_color = colors.color_name((color.red, color.green, color.blue))
        if named_color:
            svg_path.attrib["fill"] = named_color
        else:
            svg_path.attrib[
                "fill"
            ] = f"#{color.red:02x}{color.green:02x}{color.blue:02x}"

        alpha = color.alpha / 255
        if alpha != 1.0:
            svg_path.attrib["opacity"] = svg_meta.ntos(alpha)

        svg_pen = svgPathPen.SVGPathPen(None)
        transform_pen = transformPen.TransformPen(svg_pen, affine)
        ttfont["glyf"][glyph_layer.name].draw(transform_pen, ttfont["glyf"])
        # svgPathPen doesn't format #s nicely
        commands = []
        for command in svg_pen._commands:
            parts = (command[0],)
            if len(command) > 1:
                parts += tuple(float(v) for v in command[1:].split(" "))
            commands.append(svg_meta.path_segment(*parts))
        svg_path.attrib["d"] = " ".join(commands)

    return svg_root


def _colr_v1_to_svg(ttfont: ttLib.TTFont, svg_root: etree.Element):
    pass


def colr_to_svg(view_box: Rect, ttfont: ttLib.TTFont) -> Tuple[SVG]:
    """For testing only, don't use for real!"""
    assert len(ttfont["CPAL"].palettes) == 1, "We assume one palette"

    glyph_fn = _colr_v1_to_svg
    if ttfont["COLR"].version == 0:
        glyph_fn = _colr_v0_to_svg

    # TODO: COLRv1: Gradient definitions

    return tuple(
        SVG.fromstring(etree.tostring(glyph_fn(ttfont, view_box, g)))
        for g in ttfont["COLR"].ColorLayers
    )
