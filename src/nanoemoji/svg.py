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

"""Helps nanoemoji build svg fonts."""

import copy
from fontTools import ttLib
from lxml import etree  # pytype: disable=import-error
from nanoemoji.color_glyph import ColorGlyph, PaintedLayer
from nanoemoji.disjoint_set import DisjointSet
from picosvg.svg import to_element, SVG
from picosvg import svg_meta
from picosvg.svg_transform import Affine2D
import regex
from typing import MutableMapping, Sequence, Tuple


def _ensure_has_id(el: etree.Element):
    if "id" in el.attrib:
        return
    nth_child = 0
    prev = el.getprevious()
    while prev is not None:
        nth_child += 1
        prev = prev.getprevious()
    el.attrib["id"] = f'{el.getparent().attrib["id"]}::{nth_child}'


def _glyph_groups(color_glyphs: Sequence[ColorGlyph]) -> Tuple[Tuple[str, ...]]:
    """Find glyphs that need to be kept together by union find."""
    # glyphs by reuse_key
    glyphs = {}
    reuse_groups = DisjointSet()
    for color_glyph in color_glyphs:
        reuse_groups.make_set(color_glyph.glyph_name)
        for painted_layer in color_glyph.as_painted_layers():
            # TODO what attributes should go into this key for SVG
            reuse_key = _inter_glyph_reuse_key(painted_layer)
            if reuse_key not in glyphs:
                glyphs[reuse_key] = color_glyph.glyph_name
            else:
                reuse_groups.union(color_glyph.glyph_name, glyphs[reuse_key])

    return reuse_groups.sorted()


def _add_unique_gradients(
    id_updates: MutableMapping[str, str],
    svg_defs: etree.Element,
    color_glyph: ColorGlyph,
):
    for gradient in color_glyph.picosvg.xpath("//svg:defs/*"):
        gradient = copy.deepcopy(gradient)
        curr_id: str = gradient.attrib["id"]
        new_id = f"{color_glyph.glyph_name}::{curr_id}"
        del gradient.attrib["id"]
        gradient_xml: str = etree.tostring(gradient)
        if gradient_xml in id_updates:
            id_updates[curr_id] = id_updates[gradient_xml]
        else:
            gradient.attrib["id"] = new_id
            id_updates[curr_id] = new_id
            id_updates[gradient_xml] = new_id
            svg_defs.append(gradient)


def _inter_glyph_reuse_key(painted_layer: PaintedLayer):
    """Individual glyf entries, including composites, can be reused.

    SVG reuses w/paint so paint is part of key."""

    # TODO we could recycle shapes that differ only in paint, would just need to
    # transfer the paint attributes onto the use element if they differ
    return (painted_layer.paint, painted_layer.path.d, painted_layer.reuses)


def _add_glyph(svg, color_glyph, id_updates, layers):
    # each glyph gets a group of its very own
    svg_g = svg.append_to("/svg:svg", etree.Element("g"))
    svg_g.attrib["id"] = f"glyph{color_glyph.glyph_id}"

    # copy the shapes into our svg
    for painted_layer in color_glyph.as_painted_layers():
        reuse_key = _inter_glyph_reuse_key(painted_layer)
        if reuse_key not in layers:
            el = to_element(painted_layer.path)
            match = regex.match(r"url\(#([^)]+)*\)", el.attrib.get("fill", ""))
            if match:
                el.attrib[
                    "fill"
                ] = f"url(#{id_updates.get(match.group(1), match.group(1))})"
            svg_g.append(el)
            layers[reuse_key] = el
            for reuse in painted_layer.reuses:
                _ensure_has_id(el)
                svg_use = etree.SubElement(svg_g, "use")
                svg_use.attrib["href"] = f'#{el.attrib["id"]}'
                tx, ty = reuse.gettranslate()
                if tx:
                    svg_use.attrib["x"] = svg_meta.ntos(tx)
                if ty:
                    svg_use.attrib["y"] = svg_meta.ntos(ty)
                transform = reuse.translate(-tx, -ty)
                if transform != Affine2D.identity():
                    # TODO apply scale and rotation. Just slap a transform on the <use>?
                    raise NotImplementedError("TODO apply scale & rotation to use")

        else:
            el = layers[reuse_key]
            _ensure_has_id(el)
            svg_use = etree.SubElement(svg_g, "use")
            svg_use.attrib["href"] = f'#{el.attrib["id"]}'


def _update_glyph_order(
    color_glyphs: MutableMapping[str, ColorGlyph],
    ttfont: ttLib.TTFont,
    reuse_groups: Tuple[Tuple[str, ...]],
):
    # svg requires glyphs in same doc have sequential gids; reshuffle to make this true
    glyph_order = ttfont.getGlyphOrder()[: -len(color_glyphs)]
    gid = len(glyph_order)
    for group in reuse_groups:
        for glyph_name in group:
            color_glyphs[glyph_name] = color_glyphs[glyph_name]._replace(glyph_id=gid)
            gid += 1
        glyph_order.extend(group)
    ttfont.setGlyphOrder(glyph_order)


def make_svg_table(
    ttfont: ttLib.TTFont, color_glyphs: Sequence[ColorGlyph], compressed: bool = False
):
    """Build an SVG table optimizing for reuse of shapes.

    Reuse here requires putting shapes into a single svg doc. Use of large svg docs
    will come at runtime cost. A better implementation would also consider usage frequency
    and avoid taking reuse opportunities in some cases. For example, even the most
    and least popular glyphs share shapes we might choose to not take advantage of it.
    """

    reuse_groups = _glyph_groups(color_glyphs)

    color_glyphs = {c.glyph_name: c for c in color_glyphs}

    _update_glyph_order(color_glyphs, ttfont, reuse_groups)

    doc_list = []
    id_updates = {}
    layers = {}  # reusable layers
    for group in reuse_groups:
        # establish base svg, defs
        svg = SVG.fromstring(
            r'<svg version="1.1" xmlns="http://www.w3.org/2000/svg"><defs/></svg>'
        )
        svg_defs = svg.xpath_one("//svg:defs")
        for color_glyph in (color_glyphs[g] for g in group):
            _add_unique_gradients(id_updates, svg_defs, color_glyph)
            _add_glyph(svg, color_glyph, id_updates, layers)

        # print(etree.tostring(svg.svg_root, pretty_print=True).decode("utf-8"))
        gids = tuple(color_glyphs[g].glyph_id for g in group)
        doc_list.append((svg.tostring(), min(gids), max(gids)))

    svg_table = ttLib.newTable("SVG ")
    svg_table.compressed = compressed
    svg_table.docList = doc_list
    ttfont[svg_table.tableTag] = svg_table
