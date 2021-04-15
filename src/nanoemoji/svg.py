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

import dataclasses
from io import BytesIO
from fontTools import ttLib
from lxml import etree  # pytype: disable=import-error
from nanoemoji.color_glyph import ColorGlyph, PaintedLayer
from nanoemoji.disjoint_set import DisjointSet
from nanoemoji.paint import (
    Extend,
    Paint,
    PaintSolid,
    PaintLinearGradient,
    PaintRadialGradient,
    PaintGlyph,
    PaintColrGlyph,
    PaintTransform,
    PaintComposite,
    PaintColrLayers,
)
from picosvg.geometric_types import Rect
from picosvg.svg import to_element, SVG
from picosvg import svg_meta
from picosvg.svg_transform import Affine2D
from picosvg.svg_types import SVGPath
from typing import MutableMapping, NamedTuple, Optional, Sequence, Tuple, Union


# topicosvg()'s default
_DEFAULT_ROUND_NDIGITS = 3


class InterGlyphReuseKey(NamedTuple):
    view_box: Rect
    paint: Paint
    path: str
    reuses: Tuple[Affine2D]


class GradientReuseKey(NamedTuple):
    paint: Paint
    transform: Affine2D = Affine2D.identity()


_GradientPaint = Union[PaintLinearGradient, PaintRadialGradient]


@dataclasses.dataclass
class ReuseCache:
    shapes: MutableMapping[InterGlyphReuseKey, etree.Element] = dataclasses.field(
        default_factory=dict
    )
    gradient_ids: MutableMapping[GradientReuseKey, str] = dataclasses.field(
        default_factory=dict
    )


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
        for painted_layer in color_glyph.painted_layers:
            reuse_key = _inter_glyph_reuse_key(
                color_glyph.svg.view_box(), painted_layer
            )
            if reuse_key not in glyphs:
                glyphs[reuse_key] = color_glyph.glyph_name
            else:
                reuse_groups.union(color_glyph.glyph_name, glyphs[reuse_key])

    return reuse_groups.sorted()


def _ntos(n: float) -> str:
    return svg_meta.ntos(round(n, _DEFAULT_ROUND_NDIGITS))


# https://docs.microsoft.com/en-us/typography/opentype/spec/svg#coordinate-systems-and-glyph-metrics
def _svg_matrix(transform: Affine2D) -> str:
    return transform.round(_DEFAULT_ROUND_NDIGITS).tostring()


def _inter_glyph_reuse_key(
    view_box: Rect, painted_layer: PaintedLayer
) -> InterGlyphReuseKey:
    """Individual glyf entries, including composites, can be reused.
    SVG reuses w/paint so paint is part of key."""

    # TODO we could recycle shapes that differ only in paint, would just need to
    # transfer the paint attributes onto the use element if they differ
    return InterGlyphReuseKey(
        view_box, painted_layer.paint, painted_layer.path, painted_layer.reuses
    )


def _apply_solid_paint(svg_path: etree.Element, paint: PaintSolid):
    svg_path.attrib["fill"] = paint.color.opaque().to_string()
    if paint.color.alpha != 1.0:
        svg_path.attrib["opacity"] = _ntos(paint.color.alpha)


def _apply_gradient_paint(
    svg_defs: etree.Element,
    svg_path: etree.Element,
    paint: _GradientPaint,
    reuse_cache: Optional[ReuseCache] = None,
    transform: Affine2D = Affine2D.identity(),
):
    if reuse_cache is None:
        grad_id = _define_gradient(svg_defs, paint, transform)
    else:
        # Gradients can be reused by multiple glyphs in the same OT-SVG document,
        # provided paints are the same and have the same transform.
        reuse_key = GradientReuseKey(paint, transform)

        grad_id = reuse_cache.gradient_ids.get(reuse_key)
        if grad_id is None:
            grad_id = _define_gradient(svg_defs, paint, transform)
            reuse_cache.gradient_ids[reuse_key] = grad_id

    svg_path.attrib["fill"] = f"url(#{grad_id})"


def _define_gradient(
    svg_defs: etree.Element,
    paint: _GradientPaint,
    transform: Affine2D = Affine2D.identity(),
) -> str:
    if isinstance(paint, PaintLinearGradient):
        return _define_linear_gradient(svg_defs, paint, transform)
    elif isinstance(paint, PaintRadialGradient):
        return _define_radial_gradient(svg_defs, paint, transform)
    else:
        raise TypeError(type(paint))


def _apply_gradient_common_parts(
    gradient: etree.Element,
    paint: _GradientPaint,
    transform: Affine2D = Affine2D.identity(),
):
    gradient.attrib["gradientUnits"] = "userSpaceOnUse"
    for stop in paint.stops:
        stop_el = etree.SubElement(gradient, "stop")
        stop_el.attrib["offset"] = _ntos(stop.stopOffset)
        stop_el.attrib["stop-color"] = stop.color.opaque().to_string()
        if stop.color.alpha != 1.0:
            stop_el.attrib["stop-opacity"] = _ntos(stop.color.alpha)
    if paint.extend != Extend.PAD:
        gradient.attrib["spreadMethod"] = paint.extend.name.lower()

    transform = transform.round(_DEFAULT_ROUND_NDIGITS)
    if transform != Affine2D.identity():
        # Safari has a bug which makes it reject a gradient if gradientTransform
        # contains an 'involutory matrix' (i.e. matrix whose inverse equals itself,
        # such that M @ M == Identity, e.g. reflection), hence the following hack:
        # https://github.com/googlefonts/nanoemoji/issues/268
        # https://en.wikipedia.org/wiki/Involutory_matrix
        # TODO: Remove once the bug gets fixed
        if Affine2D.product(transform, transform) == Affine2D.identity():
            transform = transform._replace(a=transform.a + 0.00001)
            assert transform.inverse() != transform
        gradient.attrib["gradientTransform"] = transform.tostring()


def _define_linear_gradient(
    svg_defs: etree.Element,
    paint: PaintLinearGradient,
    transform: Affine2D = Affine2D.identity(),
) -> str:
    gradient = etree.SubElement(svg_defs, "linearGradient")
    gradient_id = gradient.attrib["id"] = f"g{len(svg_defs)}"

    p0, p1, p2 = paint.p0, paint.p1, paint.p2
    # P2 allows to rotate the linear gradient independently of the end points P0 and P1.
    # Below we compute P3 which is the orthogonal projection of P1 onto a line passing
    # through P0 and perpendicular to the "normal" or "rotation vector" from P0 and P2.
    # The vector P3-P0 is the "effective" linear gradient vector after this rotation.
    # When vector P2-P0 is perpendicular to the gradient vector P1-P0, then P3
    # (projection of P1 onto perpendicular to normal) is == P1 itself thus no rotation.
    # When P2 is collinear to the P1-P0 gradient vector, then this projected P3 == P0
    # and the gradient degenerates to a solid paint (the last color stop).
    p3 = p0 + (p1 - p0).projection((p2 - p0).perpendicular())

    x1, y1 = p0
    x2, y2 = p3
    gradient.attrib["x1"] = _ntos(x1)
    gradient.attrib["y1"] = _ntos(y1)
    gradient.attrib["x2"] = _ntos(x2)
    gradient.attrib["y2"] = _ntos(y2)

    _apply_gradient_common_parts(gradient, paint, transform)

    return gradient_id


def _define_radial_gradient(
    svg_defs: etree.Element,
    paint: PaintRadialGradient,
    transform: Affine2D = Affine2D.identity(),
) -> str:
    gradient = etree.SubElement(svg_defs, "radialGradient")
    gradient_id = gradient.attrib["id"] = f"g{len(svg_defs)}"

    if paint.c0 != paint.c1:
        fx, fy = paint.c0
        gradient.attrib["fx"] = _ntos(fx)
        gradient.attrib["fy"] = _ntos(fy)

    if paint.r0 != 0:
        gradient.attrib["fr"] = _ntos(paint.r0)

    cx, cy = paint.c1
    gradient.attrib["cx"] = _ntos(cx)
    gradient.attrib["cy"] = _ntos(cy)
    gradient.attrib["r"] = _ntos(paint.r1)

    _apply_gradient_common_parts(gradient, paint, transform)

    return gradient_id


def _map_gradient_coordinates(paint: Paint, affine: Affine2D) -> Paint:
    if isinstance(paint, PaintLinearGradient):
        return dataclasses.replace(
            paint,
            p0=affine.map_point(paint.p0),
            p1=affine.map_point(paint.p1),
            p2=affine.map_point(paint.p2),
        )
    elif isinstance(paint, PaintRadialGradient):
        scalex, scaley = affine.getscale()
        if not scalex or abs(scalex) != abs(scaley):
            raise ValueError(
                f"Expected uniform scale and/or translate, found: {affine}"
            )
        return dataclasses.replace(
            paint,
            c0=affine.map_point(paint.c0),
            c1=affine.map_point(paint.c1),
            r0=affine.map_vector((paint.r0, 0)).x,
            r1=affine.map_vector((paint.r1, 0)).x,
        )
    raise TypeError(type(paint))


def _apply_paint(
    svg_defs: etree.Element,
    svg_path: etree.Element,
    paint: Paint,
    upem_to_vbox: Affine2D,
    reuse_cache: ReuseCache,
    transform: Affine2D = Affine2D.identity(),
):
    if isinstance(paint, PaintSolid):
        _apply_solid_paint(svg_path, paint)
    elif isinstance(paint, (PaintLinearGradient, PaintRadialGradient)):
        # Gradient paint coordinates are in UPEM space, we want them in SVG viewBox
        # so that they match the SVGPath.d coordinates (that we copy unmodified).
        paint = _map_gradient_coordinates(paint, upem_to_vbox)
        # Likewise PaintTransforms refer to UPEM so they must be adjusted for SVG
        if transform != Affine2D.identity():
            transform = Affine2D.product(
                upem_to_vbox.inverse(), Affine2D.product(transform, upem_to_vbox)
            )
        _apply_gradient_paint(svg_defs, svg_path, paint, reuse_cache, transform)
    elif isinstance(paint, PaintTransform):
        transform = Affine2D.product(paint.transform, transform)
        _apply_paint(
            svg_defs, svg_path, paint.paint, upem_to_vbox, reuse_cache, transform
        )
    else:
        raise NotImplementedError(type(paint))


_XLINK_HREF_ATTR_NAME = f"{{{svg_meta.xlinkns()}}}href"


def _add_glyph(svg: SVG, color_glyph: ColorGlyph, reuse_cache: ReuseCache):
    svg_defs = svg.xpath_one("//svg:defs")

    # each glyph gets a group of its very own
    svg_g = svg.append_to("/svg:svg", etree.Element("g"))
    svg_g.attrib["id"] = f"glyph{color_glyph.glyph_id}"

    view_box = color_glyph.svg.view_box()
    if view_box is None:
        raise ValueError(f"{color_glyph.filename} must declare view box")

    # https://github.com/googlefonts/nanoemoji/issues/58: group needs transform
    svg_g.attrib["transform"] = _svg_matrix(color_glyph.transform_for_otsvg_space())

    vbox_to_upem = color_glyph.transform_for_font_space()
    upem_to_vbox = vbox_to_upem.inverse()

    # copy the shapes into our svg
    for painted_layer in color_glyph.painted_layers:
        reuse_key = _inter_glyph_reuse_key(view_box, painted_layer)
        if reuse_key not in reuse_cache.shapes:
            el = to_element(SVGPath(d=painted_layer.path))

            _apply_paint(svg_defs, el, painted_layer.paint, upem_to_vbox, reuse_cache)

            svg_g.append(el)
            reuse_cache.shapes[reuse_key] = el
        else:
            el = reuse_cache.shapes[reuse_key]
            _ensure_has_id(el)

            # we have an inter-glyph shape reuse: move the reused element to the outer
            # <defs> and replace its first occurrence with a <use>. Adobe Illustrator
            # doesn't support direct references between glyphs:
            # https://github.com/googlefonts/nanoemoji/issues/264#issuecomment-820518808
            if el not in svg_defs:
                svg_use = etree.Element("use", nsmap=svg.svg_root.nsmap)
                svg_use.attrib[_XLINK_HREF_ATTR_NAME] = f'#{el.attrib["id"]}'
                el.addnext(svg_use)
                svg_defs.append(el)  # append moves

            svg_use = etree.SubElement(svg_g, "use", nsmap=svg.svg_root.nsmap)
            svg_use.attrib[_XLINK_HREF_ATTR_NAME] = f'#{el.attrib["id"]}'

        for reuse in painted_layer.reuses:
            # intra-glyph shape reuse
            _ensure_has_id(el)
            svg_use = etree.SubElement(svg_g, "use", nsmap=svg.svg_root.nsmap)
            svg_use.attrib[_XLINK_HREF_ATTR_NAME] = f'#{el.attrib["id"]}'
            tx, ty = reuse.gettranslate()
            if tx:
                svg_use.attrib["x"] = _ntos(tx)
            if ty:
                svg_use.attrib["y"] = _ntos(ty)
            transform = reuse.translate(-tx, -ty)
            if transform != Affine2D.identity():
                svg_use.attrib["transform"] = _svg_matrix(transform)


def _ensure_ttfont_fully_decompiled(ttfont: ttLib.TTFont):
    # A TTFont might be opened lazily and some tables only partially decompiled.
    # So for this to work on any TTFont, we first compile everything to a temporary
    # stream then reload with lazy=False. Input font is modified in-place.
    tmp = BytesIO()
    ttfont.save(tmp)
    tmp.seek(0)
    ttfont2 = ttLib.TTFont(tmp, lazy=False)
    for tag in ttfont2.keys():
        table = ttfont2[tag]
        # cmap is exceptional in that it always loads subtables lazily upon getting
        # their attributes, no matter the value of TTFont.lazy option.
        # TODO: remove this hack once fixed in fonttools upstream
        if tag == "cmap":
            _ = [st.cmap for st in table.tables]
        ttfont[tag] = table


def _ensure_groups_grouped_in_glyph_order(
    color_glyphs: MutableMapping[str, ColorGlyph],
    color_glyph_order: Sequence[str],
    ttfont: ttLib.TTFont,
    reuse_groups: Tuple[Tuple[str, ...]],
):
    # svg requires glyphs in same doc have sequential gids; reshuffle to make this true.

    # Changing the order of glyphs in a TTFont requires that all tables that use
    # glyph indexes have been fully decompiled (loaded with lazy=False).
    # Cf. https://github.com/fonttools/fonttools/issues/2060
    _ensure_ttfont_fully_decompiled(ttfont)

    # The glyph names in the TTFont may have been dropped (post table 3.0), so the
    # names we see after decompiling the TTFont are made up and likely different
    # from the input color glyph names. We only want to reorder the glyphs while
    # keeping the existing names, we can't change order and rename at the same time
    # or else tables that contain mappings keyed by glyph name would blow up.
    # Thus, we need to match the old and current names by their position in the
    # font's current glyph order: i.e. we assume all color glyphs are placed at the
    # END of the glyph order.
    current_glyph_order = ttfont.getGlyphOrder()
    current_color_glyph_names = current_glyph_order[-len(color_glyphs) :]
    assert len(color_glyph_order) == len(current_color_glyph_names)
    rename_map = {
        color_glyph_order[i]: current_color_glyph_names[i]
        for i in range(len(color_glyph_order))
    }

    glyph_order = current_glyph_order[: -len(color_glyphs)]
    gid = len(glyph_order)
    for group in reuse_groups:
        for glyph_name in group:
            color_glyphs[glyph_name] = color_glyphs[glyph_name]._replace(glyph_id=gid)
            gid += 1
        glyph_order.extend(rename_map[g] for g in group)
    ttfont.setGlyphOrder(glyph_order)


def _picosvg_docs(
    ttfont: ttLib.TTFont, color_glyphs: Sequence[ColorGlyph]
) -> Sequence[Tuple[str, int, int]]:
    reuse_groups = _glyph_groups(color_glyphs)
    color_glyph_order = [c.glyph_name for c in color_glyphs]
    color_glyphs = {c.glyph_name: c for c in color_glyphs}
    _ensure_groups_grouped_in_glyph_order(
        color_glyphs, color_glyph_order, ttfont, reuse_groups
    )

    doc_list = []
    for group in reuse_groups:
        reuse_cache = ReuseCache()
        # establish base svg, defs
        root = etree.Element(
            f"{{{svg_meta.svgns()}}}svg",
            {"version": "1.1"},
            nsmap={None: svg_meta.svgns(), "xlink": svg_meta.xlinkns()},
        )
        defs = etree.SubElement(root, f"{{{svg_meta.svgns()}}}defs", nsmap=root.nsmap)
        svg = SVG(root)

        for color_glyph in (color_glyphs[g] for g in group):
            _add_glyph(svg, color_glyph, reuse_cache)

        # if there are no gradients, strip the empty <defs/>
        if len(defs) == 0:
            root.remove(defs)

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
            # all the scaling and positioning happens in "transform" below
            .remove_attributes(("width", "height", "viewBox"), inplace=True)
            # Firefox likes to render blank if present
            .remove_attributes(("enable-background",), inplace=True)
        )
        g = etree.Element(
            "g",
            {
                # Map gid => svg doc
                "id": f"glyph{color_glyph.glyph_id}",
                # map viewBox to OT-SVG space (+x,-y)
                "transform": _svg_matrix(color_glyph.transform_for_otsvg_space()),
            },
        )
        # move all the elements under the new group
        g.extend(svg.svg_root)
        svg.svg_root.append(g)

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
