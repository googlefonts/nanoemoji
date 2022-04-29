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
from itertools import groupby
from fontTools import ttLib
from functools import reduce
from lxml import etree  # pytype: disable=import-error
from nanoemoji.colors import Color
from nanoemoji.color_glyph import map_viewbox_to_otsvg_space, ColorGlyph
from nanoemoji.config import FontConfig
from nanoemoji.disjoint_set import DisjointSet
from nanoemoji.glyph_reuse import GlyphReuseCache
from nanoemoji.paint import (
    _BasePaintTransform,
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
)
from nanoemoji.parts import ReusableParts
from nanoemoji.reorder_glyphs import reorder_glyphs
from picosvg.geometric_types import Rect
from picosvg import svg_meta
from picosvg.svg import to_element, SVG, SVGTraverseContext
from picosvg.svg_reuse import normalize, affine_between
from picosvg.svg_transform import parse_svg_transform, Affine2D
from picosvg.svg_types import SVGPath
from typing import (
    cast,
    Iterable,
    Mapping,
    MutableMapping,
    NamedTuple,
    Optional,
    Set,
    Sequence,
    Tuple,
    Union,
)


# topicosvg()'s default
_DEFAULT_ROUND_NDIGITS = 3


class GradientReuseKey(NamedTuple):
    paint: Paint
    transform: Affine2D = Affine2D.identity()


_GradientPaint = Union[PaintLinearGradient, PaintRadialGradient]


@dataclasses.dataclass
class ReuseCache:
    glyph_cache: GlyphReuseCache
    glyph_elements: MutableMapping[str, etree.Element] = dataclasses.field(
        default_factory=dict
    )
    gradient_ids: MutableMapping[GradientReuseKey, str] = dataclasses.field(
        default_factory=dict
    )

    def add_glyph(
        self,
        glyph_name: str,
        glyph_path: str,
    ):
        assert glyph_name not in self.glyph_elements, f"Second addition of {glyph_name}"
        self.glyph_elements[glyph_name] = to_element(SVGPath(d=glyph_path))

    def reuse_spans_glyphs(self, path: str) -> bool:
        return (
            len(
                {
                    _color_glyph_name(gn)
                    for gn in self.glyph_cache.consuming_glyphs(path)
                }
            )
            > 1
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


def _paint_glyph_name(color_glyph: ColorGlyph, nth: int) -> str:
    return f"{color_glyph.ufo_glyph_name}.{nth}"


def _color_glyph_name(glyph_name: str) -> str:
    return glyph_name[: glyph_name.rindex(".")]


def _paint_glyphs(color_glyph: ColorGlyph) -> Iterable[PaintGlyph]:
    for root in color_glyph.painted_layers:
        for context in root.breadth_first():
            # Group glyphs based on common shapes
            if not isinstance(context.paint, PaintGlyph):
                continue
            yield cast(PaintGlyph, context.paint)


def _glyph_groups(
    config: FontConfig,
    color_glyphs: Sequence[ColorGlyph],
    reusable_parts: ReusableParts,
) -> Tuple[Tuple[str, ...]]:
    """Find glyphs that need to be kept together by union find."""

    # This cache is solely to help us group
    glyph_cache = GlyphReuseCache(reusable_parts)

    # Make sure we keep together color glyphs that share shapes
    reuse_groups = DisjointSet()  # ensure glyphs sharing shapes are in the same doc
    for color_glyph in color_glyphs:
        reuse_groups.make_set(color_glyph.ufo_glyph_name)
        nth_paint_glyph = 0
        for root in color_glyph.painted_layers:
            for context in root.breadth_first():
                # Group glyphs based on common shapes
                if not isinstance(context.paint, PaintGlyph):
                    continue

                paint_glyph = cast(PaintGlyph, context.paint)
                maybe_reuse = glyph_cache.try_reuse(
                    paint_glyph.glyph, color_glyph.svg.view_box()
                )

                if glyph_cache.is_known_path(maybe_reuse.shape):
                    # we've seen this exact path before, join the union with other consumers
                    reuse_groups.union(
                        color_glyph.ufo_glyph_name,
                        _color_glyph_name(
                            glyph_cache.get_glyph_for_path(maybe_reuse.shape)
                        ),
                    )
                else:
                    # I claim this path in the name of myself!
                    # Use a path-specific name so each color glyph can register multiple paths
                    paint_glyph_name = _paint_glyph_name(color_glyph, nth_paint_glyph)
                    glyph_cache.set_glyph_for_path(paint_glyph_name, maybe_reuse.shape)

                nth_paint_glyph += 1

    return reuse_groups.sorted()


def _ntos(n: float) -> str:
    return svg_meta.ntos(round(n, _DEFAULT_ROUND_NDIGITS))


# https://docs.microsoft.com/en-us/typography/opentype/spec/svg#coordinate-systems-and-glyph-metrics
def _svg_matrix(transform: Affine2D) -> str:
    return transform.round(_DEFAULT_ROUND_NDIGITS).tostring()


def _apply_solid_paint(el: etree.Element, paint: PaintSolid):
    if etree.QName(el.tag).localname == "g":
        assert paint.color.opaque() == Color.fromstring(
            "black"
        ), "Unexpected color choice"
    if paint.color.opaque() != Color.fromstring("black"):
        el.attrib["fill"] = paint.color.opaque().to_string()
    if paint.color.alpha != 1.0:
        el.attrib["opacity"] = _ntos(paint.color.alpha)


def _apply_gradient_paint(
    svg_defs: etree.Element,
    svg_path: etree.Element,
    paint: _GradientPaint,
    reuse_cache: ReuseCache,
    transform: Affine2D = Affine2D.identity(),
):
    if reuse_cache is None:
        grad_id = _define_gradient(svg_defs, paint, transform)
    else:
        # Gradients can be reused by multiple glyphs in the same OT-SVG document,
        # provided paints are the same and have the same transform.
        # Pre-apply transform to gradient's geometry and round both to
        # normalize them before adding to the cache, thus increasing the chance
        # of a reuse.
        if not transform.almost_equals(Affine2D.identity()):
            paint = paint.apply_transform(transform, check_overflows=False)
            transform = Affine2D.identity()
            if is_transform(paint):
                paint = cast(_BasePaintTransform, paint)
                transform, paint = paint.gettransform(), paint.paint
        paint = cast(_GradientPaint, paint)
        paint = paint.round(_DEFAULT_ROUND_NDIGITS)
        transform = transform.round(_DEFAULT_ROUND_NDIGITS)
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
        if transform @ transform == Affine2D.identity():
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


def _map_gradient_coordinates(
    paint: _GradientPaint, affine: Affine2D
) -> _GradientPaint:
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


def _is_svg_supported_composite(paint: Paint) -> bool:
    # Only simple group opacity for now because that's all we produce in color_glyph.py
    return (
        isinstance(paint, PaintComposite)
        and paint.mode == CompositeMode.SRC_IN
        and isinstance(paint.backdrop, PaintSolid)
    )


_XLINK_HREF_ATTR_NAME = f"{{{svg_meta.xlinkns()}}}href"
_PAINT_ATTRIB_APPLY_PAINT_MAY_SET = {"fill", "opacity"}


def _apply_paint(
    svg_defs: etree.Element,
    el: etree.Element,
    paint: Paint,
    upem_to_vbox: Affine2D,
    reuse_cache: ReuseCache,
    transform: Affine2D = Affine2D.identity(),
):
    # If you modify the attributes _apply_paint can set also modify _PAINT_ATTRIB_APPLY_PAINT_MAY_SET
    if isinstance(paint, PaintSolid):
        _apply_solid_paint(el, paint)
    elif isinstance(paint, (PaintLinearGradient, PaintRadialGradient)):
        # Gradient paint coordinates are in UPEM space, we want them in SVG viewBox
        # so that they match the SVGPath.d coordinates (that we copy unmodified).
        paint = _map_gradient_coordinates(paint, upem_to_vbox)
        # Likewise transforms refer to UPEM so they must be adjusted for SVG
        if transform != Affine2D.identity():
            transform = Affine2D.compose_ltr(
                (upem_to_vbox.inverse(), transform, upem_to_vbox)
            )
        _apply_gradient_paint(svg_defs, el, paint, reuse_cache, transform)
    elif is_transform(paint):
        transform @= paint.gettransform()
        child = paint.paint  # pytype: disable=attribute-error
        _apply_paint(svg_defs, el, child, upem_to_vbox, reuse_cache, transform)
    else:
        raise NotImplementedError(type(paint))


def _attrib_apply_paint_uses(el: etree.Element) -> Set[str]:
    # Per https://developer.mozilla.org/en-US/docs/Web/SVG/Element/use
    # only a few attributes of target can be overriden by <use>. However, we need
    # only concern ourselves with the subset of those that _apply_paint might set.
    return set(el.attrib) & _PAINT_ATTRIB_APPLY_PAINT_MAY_SET


def _migrate_to_defs(
    svg: SVG,
    reused_el: etree.Element,
    reuse_cache: ReuseCache,
    glyph_name: str,
):
    svg_defs = svg.xpath_one("//svg:defs")

    if reused_el in svg_defs:
        return  # nop

    tag = etree.QName(reused_el.tag).localname
    assert tag == "path", f"expected 'path', found '{tag}'"

    svg_use = etree.Element("use", nsmap=svg.svg_root.nsmap)
    svg_use.attrib[_XLINK_HREF_ATTR_NAME] = f"#{glyph_name}"
    reused_el.addnext(svg_use)

    svg_defs.append(reused_el)  # append moves

    # sorted for diff stability
    for attr_name in sorted(_attrib_apply_paint_uses(reused_el)):
        svg_use.attrib[attr_name] = reused_el.attrib.pop(attr_name)

    return svg_use


def _transform(el: etree.Element, transform: Affine2D):
    if transform.almost_equals(Affine2D.identity()):
        return

    # offset-only use is nice and tidy
    tx, ty = transform.gettranslate()
    if el.tag == "use" and transform.translate(-tx, -ty).almost_equals(
        Affine2D.identity()
    ):
        if tx:
            el.attrib["x"] = _ntos(tx)
        if ty:
            el.attrib["y"] = _ntos(ty)
    else:
        el.attrib["transform"] = _svg_matrix(transform)


def _create_use_element(
    svg: SVG, parent_el: etree.Element, glyph_name: str, transform: Affine2D
) -> etree.Element:
    svg_use = etree.SubElement(parent_el, "use", nsmap=svg.svg_root.nsmap)
    svg_use.attrib[_XLINK_HREF_ATTR_NAME] = f"#{glyph_name}"
    _transform(svg_use, transform)
    return svg_use


def _font_units_to_svg_units(
    view_box: Rect, config: FontConfig, glyph_width: int
) -> Affine2D:
    return map_viewbox_to_otsvg_space(
        view_box,
        config.ascender,
        config.descender,
        glyph_width,
        config.transform,
    )


def _svg_units_to_font_units(
    view_box: Rect, config: FontConfig, glyph_width: int
) -> Affine2D:
    return map_viewbox_to_otsvg_space(
        view_box,
        config.ascender,
        config.descender,
        glyph_width,
        config.transform,
    )


def _add_glyph(
    config: FontConfig, svg: SVG, color_glyph: ColorGlyph, reuse_cache: ReuseCache
):
    svg_defs = svg.xpath_one("//svg:defs")

    # each glyph gets a group of its very own
    svg_g = svg.append_to("/svg:svg", etree.Element("g"))
    svg_g.attrib["id"] = f"glyph{color_glyph.glyph_id}"

    view_box = color_glyph.svg.view_box()
    if view_box is None:
        raise ValueError(f"{color_glyph.svg_filename} must declare view box")

    # https://github.com/googlefonts/nanoemoji/issues/58: group needs transform
    transform = _font_units_to_svg_units(
        reuse_cache.glyph_cache.view_box(), config, color_glyph.ufo_glyph.width
    )
    if not transform.almost_equals(Affine2D.identity()):
        svg_g.attrib["transform"] = _svg_matrix(transform)

    vbox_to_upem = _svg_units_to_font_units(
        reuse_cache.glyph_cache.view_box(), config, color_glyph.ufo_glyph.width
    )
    upem_to_vbox = vbox_to_upem.inverse()

    # copy the shapes into our svg
    el_by_path = {(): svg_g}
    complete_paths = set()
    nth_paint_glyph = 0

    for root in color_glyph.painted_layers:
        for context in root.breadth_first():
            if any(c == context.path[: len(c)] for c in complete_paths):
                continue

            parent_el = svg_g
            path = context.path
            while path:
                if path in el_by_path:
                    parent_el = el_by_path[path]
                    break
                path = path[:-1]

            if isinstance(context.paint, PaintGlyph):
                paint = cast(PaintGlyph, context.paint)
                glyph_name = _paint_glyph_name(color_glyph, nth_paint_glyph)

                assert paint.glyph.startswith(
                    "M"
                ), f"{paint.glyph} doesn't look like a path"

                maybe_reuse = reuse_cache.glyph_cache.try_reuse(
                    paint.glyph, color_glyph.svg.view_box()
                )

                # if we have a glyph for the shape already, use that
                if reuse_cache.glyph_cache.is_known_path(maybe_reuse.shape):
                    reused_glyph_name = reuse_cache.glyph_cache.get_glyph_for_path(
                        maybe_reuse.shape
                    )
                    svg_use = _create_use_element(
                        svg, parent_el, reused_glyph_name, maybe_reuse.transform
                    )

                    # the reused glyph will already exist, but it may need adjustment on grounds of reuse
                    reused_el = reuse_cache.glyph_elements[reused_glyph_name]
                    reused_el.attrib["id"] = reused_glyph_name  # hard to target w/o id

                    # In two cases, we need to push the reused element to the outer
                    # <defs> and replace its first occurence with a <use>:
                    # 1) If reuse spans multiple glyphs, as Adobe Illustrator
                    #    doesn't support direct references between glyphs:
                    #    https://github.com/googlefonts/nanoemoji/issues/264
                    # 2) If the reused_el has attributes <use> cannot override
                    #    https://github.com/googlefonts/nanoemoji/issues/337
                    # We don't know if #1 holds so to make life simpler just always
                    # promote reused glyphs to defs
                    _migrate_to_defs(svg, reused_el, reuse_cache, reused_glyph_name)

                    # We must apply the inverse of the reuse transform to the children
                    # paints to discount its effect on them, since these refer to the
                    # original pre-reuse paths. _apply_paint expects 'transform' to be
                    # in UPEM space, whereas maybe_reuse.transform is in SVG space, so
                    # we remap the (inverse of the) latter from SVG to UPEM.
                    inverse_reuse_transform = Affine2D.compose_ltr(
                        (
                            upem_to_vbox,
                            maybe_reuse.transform.inverse(),
                            upem_to_vbox.inverse(),
                        )
                    )

                    _apply_paint(
                        svg_defs,
                        svg_use,
                        paint.paint,
                        upem_to_vbox,
                        reuse_cache,
                        inverse_reuse_transform,
                    )
                else:
                    # otherwise, create a glyph for the target and use it
                    reuse_cache.glyph_cache.set_glyph_for_path(
                        glyph_name, maybe_reuse.shape
                    )
                    reuse_cache.add_glyph(glyph_name, maybe_reuse.shape)
                    el = reuse_cache.glyph_elements[glyph_name]

                    _apply_paint(
                        svg_defs,
                        el,
                        context.paint.paint,  # pytype: disable=attribute-error
                        upem_to_vbox,
                        reuse_cache,
                    )

                    # If we need a transformed version of the path do it by wrapping a g around
                    # to ensure anyone else who reuses the shape doesn't pick up our transform
                    if not maybe_reuse.transform.almost_equals(Affine2D.identity()):
                        g = etree.Element("g")
                        _transform(g, maybe_reuse.transform)
                        g.append(el)
                        el = g

                    parent_el.append(el)  # pytype: disable=attribute-error

                # don't update el_by_path because we're declaring this path complete
                complete_paths.add(context.path + (context.paint,))
                nth_paint_glyph += 1

            elif isinstance(context.paint, PaintColrLayers):
                pass

            elif isinstance(context.paint, PaintSolid):
                _apply_solid_paint(parent_el, context.paint)

            elif _is_svg_supported_composite(context.paint):
                el = etree.SubElement(parent_el, f"{{{svg_meta.svgns()}}}g")
                el_by_path[context.path + (context.paint,)] = el

            # TODO: support transform types, either by introducing <g> or by applying context.transform to Paint

            else:
                raise ValueError(f"What do we do with {context}")


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

    # We kept glyph names stable when saving a font for svg so it's safe to match on
    assert ttfont["post"].formatType == 2, "glyph names need to be stable"

    # everything that *isn't* shuffling
    group_glyphs = reduce(lambda a, c: a | set(c), reuse_groups, set())
    glyph_order = [g for g in ttfont.getGlyphOrder() if g not in group_glyphs]

    # plus everything that is shuffling, in the order it needs to stay in
    # update color glyph gid as we go
    gid = len(glyph_order)
    for group in reuse_groups:
        for glyph_name in group:
            glyph_order.append(glyph_name)
            color_glyphs[glyph_name] = color_glyphs[glyph_name]._replace(glyph_id=gid)
            gid += 1

    assert len(glyph_order) == len(set(glyph_order)), ", ".join(glyph_order)
    assert len(ttfont.getGlyphOrder()) == len(glyph_order) and set(
        ttfont.getGlyphOrder()
    ) == set(
        glyph_order
    ), f"lhs only {set(ttfont.getGlyphOrder()) - set(glyph_order)} rhs only {set(glyph_order) - set(ttfont.getGlyphOrder())}"

    reorder_glyphs(ttfont, glyph_order)


def _use_href(use_el):
    ref = use_el.attrib[_XLINK_HREF_ATTR_NAME]
    assert ref.startswith("#"), f"Only use #fragment supported, reject {ref}"
    return ref[1:]


def _tidy_use_elements(svg: SVG):
    use_els = sorted(svg.xpath("//use"), key=_use_href)
    targets = {}

    for use_el in use_els:
        ref = _use_href(use_el)
        reused_el = svg.xpath_one(f'//svg:*[@id="{ref}"]')
        targets[ref] = reused_el

        duplicate_attrs = {
            attr_name
            for attr_name, attr_value in use_el.attrib.items()
            if attr_name in reused_el.attrib
            and attr_value == reused_el.attrib.get(attr_name)
        }
        for duplicate_attr in duplicate_attrs:
            del use_el.attrib[duplicate_attr]

        # if the parent is a transform-only group migrate the transform to the use
        if use_el.getparent().tag == "g" and set(use_el.getparent().attrib.keys()) == {
            "transform"
        }:
            g = use_el.getparent()
            g.addnext(use_el)
            _transform(use_el, parse_svg_transform(g.attrib["transform"]))
            g.getparent().remove(g)

    # If all <use> have the same paint attr migrate it from use to target
    for ref, uses in groupby(use_els, key=_use_href):
        uses = list(uses)
        target = targets[ref]
        for attr_name in sorted(_PAINT_ATTRIB_APPLY_PAINT_MAY_SET):
            values = [use.attrib[attr_name] for use in uses if attr_name in use.attrib]
            unique_values = set(values)
            if len(values) == len(uses) and len(unique_values) == 1:
                target.attrib[attr_name] = values[0]
                for use in uses:
                    del use.attrib[attr_name]


def _picosvg_docs(
    config: FontConfig,
    reusable_parts: ReusableParts,
    ttfont: ttLib.TTFont,
    color_glyphs: Sequence[ColorGlyph],
) -> Sequence[Tuple[str, int, int]]:
    reuse_groups = _glyph_groups(config, color_glyphs, reusable_parts)
    color_glyph_order = [c.ufo_glyph_name for c in color_glyphs]
    color_glyphs = {c.ufo_glyph_name: c for c in color_glyphs}
    _ensure_groups_grouped_in_glyph_order(
        color_glyphs, color_glyph_order, ttfont, reuse_groups
    )

    doc_list = []
    for group in reuse_groups:
        # reuse is only possible within a single doc so process each individually
        # we created our reuse groups specifically to ensure glyphs that share are together
        reuse_cache = ReuseCache(GlyphReuseCache(reusable_parts))

        # establish base svg, defs
        root = etree.Element(
            f"{{{svg_meta.svgns()}}}svg",
            {"version": "1.1"},
            nsmap={None: svg_meta.svgns(), "xlink": svg_meta.xlinkns()},
        )
        etree.SubElement(root, f"{{{svg_meta.svgns()}}}defs", nsmap=root.nsmap)
        svg = SVG(root)
        del root  # SVG could change root, shouldn't matter for us

        for color_glyph in (color_glyphs[g] for g in group):
            if color_glyph.painted_layers:
                _add_glyph(config, svg, color_glyph, reuse_cache)

        # tidy use elements, they may emerge from _add_glyph with unnecessary attributes
        _tidy_use_elements(svg)

        # sort <defs> by @id to increase diff stability
        defs = svg.xpath_one("//svg:defs")
        defs[:] = sorted(defs, key=lambda e: e.attrib["id"])

        # strip <defs/> if empty
        if len(defs) == 0:
            svg.svg_root.remove(defs)

        if len(svg.svg_root) == 0:
            continue

        gids = tuple(color_glyphs[g].glyph_id for g in group)
        doc_list.append(
            (svg.tostring(pretty_print=config.pretty_print), min(gids), max(gids))
        )

    return doc_list


def _rawsvg_docs(
    config: FontConfig, ttfont: ttLib.TTFont, color_glyphs: Sequence[ColorGlyph]
) -> Sequence[Tuple[str, int, int]]:
    doc_list = []
    for color_glyph in color_glyphs:
        svg = (
            # all the scaling and positioning happens in "transform" below
            color_glyph.svg.remove_attributes(("width", "height", "viewBox"))
            # Firefox likes to render blank if present
            .remove_attributes(("enable-background",), inplace=True)
        )
        g = etree.Element(
            "g",
            {
                # Map gid => svg doc
                "id": f"glyph{color_glyph.glyph_id}",
                # map viewBox to OT-SVG space (+x,-y)
                "transform": _svg_matrix(
                    _font_units_to_svg_units(
                        color_glyph.svg.view_box(), config, color_glyph.ufo_glyph.width
                    )
                ),
            },
        )
        # move all the elements under the new group
        g.extend(svg.svg_root)
        svg.svg_root.append(g)

        doc_list.append(
            (
                svg.tostring(pretty_print=config.pretty_print),
                color_glyph.glyph_id,
                color_glyph.glyph_id,
            )
        )
    return doc_list


def make_svg_table(
    config: FontConfig,
    reusable_parts: ReusableParts,
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
        doc_list = _picosvg_docs(config, reusable_parts, ttfont, color_glyphs)
    else:
        doc_list = _rawsvg_docs(config, ttfont, color_glyphs)

    svg_table = ttLib.newTable("SVG ")
    svg_table.compressed = compressed
    svg_table.docList = doc_list
    ttfont[svg_table.tableTag] = svg_table
