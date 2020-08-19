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
import dataclasses
from fontTools import ttLib
from lxml import etree  # pytype: disable=import-error
from nanoemoji.color_glyph import ColorGlyph, PaintedLayer
from nanoemoji.disjoint_set import DisjointSet
from picosvg.geometric_types import Rect
from picosvg.svg import to_element, SVG
from picosvg import svg_meta
from picosvg.svg_transform import Affine2D
import regex
from typing import MutableMapping, Sequence, Tuple


@dataclasses.dataclass
class ReuseCache:
    old_to_new_id: MutableMapping[str, str] = dataclasses.field(default_factory=dict)
    gradient_to_id: MutableMapping[str, str] = dataclasses.field(default_factory=dict)
    shapes: MutableMapping[str, etree.Element] = dataclasses.field(default_factory=dict)


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
            reuse_key = _inter_glyph_reuse_key(
                color_glyph.picosvg.view_box(), painted_layer
            )
            if reuse_key not in glyphs:
                glyphs[reuse_key] = color_glyph.glyph_name
            else:
                reuse_groups.union(color_glyph.glyph_name, glyphs[reuse_key])

    return reuse_groups.sorted()


def _add_unique_gradients(
    svg_defs: etree.Element, color_glyph: ColorGlyph, reuse_cache: ReuseCache,
):
    for gradient in color_glyph.picosvg.xpath("//svg:defs/*"):
        gradient = copy.deepcopy(gradient)
        curr_id: str = gradient.attrib["id"]
        new_id = f"{color_glyph.glyph_name}::{curr_id}"
        del gradient.attrib["id"]
        gradient_xml: str = etree.tostring(gradient)
        if gradient_xml in reuse_cache.gradient_to_id:
            reuse_cache.old_to_new_id[curr_id] = reuse_cache.gradient_to_id[
                gradient_xml
            ]
        else:
            gradient.attrib["id"] = new_id
            reuse_cache.old_to_new_id[curr_id] = new_id
            reuse_cache.gradient_to_id[gradient_xml] = new_id
            svg_defs.append(gradient)


def _ntos(n: float) -> str:
    return svg_meta.ntos(round(n, 3))


# https://docs.microsoft.com/en-us/typography/opentype/spec/svg#coordinate-systems-and-glyph-metrics
def _svg_matrix(transform: Affine2D) -> str:
    # TODO handle rotation: Affine2D uses radiens, svg is in degrees
    return f'matrix({" ".join((_ntos(v) for v in transform))})'


def _inter_glyph_reuse_key(view_box: Rect, painted_layer: PaintedLayer):
    """Individual glyf entries, including composites, can be reused.

    SVG reuses w/paint so paint is part of key."""

    # TODO we could recycle shapes that differ only in paint, would just need to
    # transfer the paint attributes onto the use element if they differ
    return (view_box, painted_layer.paint, painted_layer.path.d, painted_layer.reuses)


def _add_glyph(svg: SVG, color_glyph: ColorGlyph, reuse_cache: ReuseCache):
    # each glyph gets a group of its very own
    svg_g = svg.append_to("/svg:svg", etree.Element("g"))
    svg_g.attrib["id"] = f"glyph{color_glyph.glyph_id}"
    # https://github.com/googlefonts/nanoemoji/issues/58: group needs transform
    svg_g.attrib["transform"] = _svg_matrix(color_glyph.transform_for_otsvg_space())

    # copy the shapes into our svg
    for painted_layer in color_glyph.as_painted_layers():
        view_box = color_glyph.picosvg.view_box()
        if view_box is None:
            raise ValueError(f"{color_glyph.filename} must declare view box")
        reuse_key = _inter_glyph_reuse_key(view_box, painted_layer)
        if reuse_key not in reuse_cache.shapes:
            el = to_element(painted_layer.path)
            match = regex.match(r"url\(#([^)]+)*\)", el.attrib.get("fill", ""))
            if match:
                el.attrib[
                    "fill"
                ] = f"url(#{reuse_cache.old_to_new_id.get(match.group(1), match.group(1))})"
            svg_g.append(el)
            reuse_cache.shapes[reuse_key] = el
            for reuse in painted_layer.reuses:
                _ensure_has_id(el)
                svg_use = etree.SubElement(svg_g, "use")
                svg_use.attrib["href"] = f'#{el.attrib["id"]}'
                tx, ty = reuse.gettranslate()
                if tx:
                    svg_use.attrib["x"] = _ntos(tx)
                if ty:
                    svg_use.attrib["y"] = _ntos(ty)
                transform = reuse.translate(-tx, -ty)
                if transform != Affine2D.identity():
                    # TODO apply scale and rotation. Just slap a transform on the <use>?
                    raise NotImplementedError("TODO apply scale & rotation to use")

        else:
            el = reuse_cache.shapes[reuse_key]
            _ensure_has_id(el)
            svg_use = etree.SubElement(svg_g, "use")
            svg_use.attrib["href"] = f'#{el.attrib["id"]}'


def _ensure_groups_grouped_in_glyph_order(
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


def _picosvg_docs(
    ttfont: ttLib.TTFont, color_glyphs: Sequence[ColorGlyph]
) -> Sequence[Tuple[str, int, int]]:
    reuse_groups = _glyph_groups(color_glyphs)
    color_glyphs = {c.glyph_name: c for c in color_glyphs}
    _ensure_groups_grouped_in_glyph_order(color_glyphs, ttfont, reuse_groups)

    doc_list = []
    reuse_cache = ReuseCache()
    layers = {}  # reusable layers
    for group in reuse_groups:
        # establish base svg, defs
        svg = SVG.fromstring(
            r'<svg version="1.1" xmlns="http://www.w3.org/2000/svg"><defs/></svg>'
        )

        svg_defs = svg.xpath_one("//svg:defs")
        for color_glyph in (color_glyphs[g] for g in group):
            _add_unique_gradients(svg_defs, color_glyph, reuse_cache)
            _add_glyph(svg, color_glyph, reuse_cache)

        gids = tuple(color_glyphs[g].glyph_id for g in group)
        doc_list.append((svg.tostring(), min(gids), max(gids)))
    return doc_list


def _rawsvg_docs(
    ttfont: ttLib.TTFont, color_glyphs: Sequence[ColorGlyph]
) -> Sequence[Tuple[str, int, int]]:
    doc_list = []
    for color_glyph in color_glyphs:
        svg = (
            SVG.parse(color_glyph.filename)
            # dumb sizing isn't useful
            .remove_attributes(("width", "height"), inplace=True)
            # Firefox likes to render blank if present
            .remove_attributes(("enable-background",), inplace=True)
            # Map gid => svg doc
            .set_attributes((("id", f"glyph{color_glyph.glyph_id}"),))
        )
        svg.svg_root.attrib[
            "transform"
        ] = f"translate(0, {-color_glyph.ufo.info.unitsPerEm})"
        doc_list.append((svg.tostring(), color_glyph.glyph_id, color_glyph.glyph_id))
    return doc_list


def make_svg_table(
    ttfont: ttLib.TTFont,
    color_glyphs: Sequence[ColorGlyph],
    picosvg: bool,
    compressed: bool = False,
):
    """Build an SVG table optimizing for reuse of shapes.

    Reuse here requires putting shapes into a single svg doc. Use of large svg docs
    will come at runtime cost. A better implementation would also consider usage frequency
    and avoid taking reuse opportunities in some cases. For example, even the most
    and least popular glyphs share shapes we might choose to not take advantage of it.
    """

    if picosvg:
        doc_list = _picosvg_docs(ttfont, color_glyphs)
    else:
        doc_list = _rawsvg_docs(ttfont, color_glyphs)

    svg_table = ttLib.newTable("SVG ")
    svg_table.compressed = compressed
    svg_table.docList = doc_list
    ttfont[svg_table.tableTag] = svg_table
