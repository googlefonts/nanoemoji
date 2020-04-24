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
import collections
from itertools import chain
from lxml import etree
from picosvg.geometric_types import Point, Rect
from picosvg.svg_transform import Affine2D
from nanoemoji.colors import Color
from nanoemoji import glyph
from nanoemoji.paint import (
    Extend,
    ColorStop,
    PaintLinearGradient,
    PaintRadialGradient,
    PaintSolid,
)


def _map_viewbox_to_emsquare(view_box, upem):
    # scale to font upem
    x_scale = upem / view_box.w
    y_scale = upem / view_box.h
    # shift so origin is 0,0
    dx = -view_box.x * x_scale
    dy = -view_box.y * y_scale
    # flip y axis and shift so things are in the right place
    y_scale = -y_scale
    dy = dy + upem
    return Affine2D(x_scale, 0, 0, y_scale, dx, dy)


def _get_gradient_units_relative_scale(grad_el, view_box):
    gradient_units = grad_el.attrib.get("gradientUnits", "objectBoundingBox")
    if gradient_units == "userSpaceOnUse":
        # For gradientUnits="userSpaceOnUse", percentages represent values relative to
        # the current viewport. Here we use the width and height of the viewBox.
        return view_box.w, view_box.h
    elif gradient_units == "objectBoundingBox":
        # For gradientUnits="objectBoundingBox", percentages represent values relative
        # to the object bounding box. The latter defines an abstract coordinate system
        # with origin at (0,0) and a nominal width and height = 1.
        return 1, 1
    else:
        raise ValueError(
            '<linearGradient gradientUnits="{gradient_units!r}"/> not supported'
        )


def _get_gradient_transform(grad_el, shape_bbox, view_box, upem):
    transform = _map_viewbox_to_emsquare(view_box, upem)

    gradient_units = grad_el.attrib.get("gradientUnits", "objectBoundingBox")
    if gradient_units == "objectBoundingBox":
        bbox_space = Rect(0, 0, 1, 1)
        bbox_transform = Affine2D.rect_to_rect(bbox_space, shape_bbox)
        transform = transform.concat(bbox_transform)

    if "gradientTransform" in grad_el.attrib:
        gradient_transform = Affine2D.fromstring(grad_el.attrib["gradientTransform"])
        transform = transform.concat(gradient_transform)

    return transform


def _number_or_percentage(s: str, scale=1) -> float:
    return float(s[:-1]) / 100 * scale if s.endswith("%") else float(s)


def _parse_linear_gradient(grad_el, shape_bbox, view_box, upem):
    width, height = _get_gradient_units_relative_scale(grad_el, view_box)

    x1 = _number_or_percentage(grad_el.attrib.get("x1", "0%"), width)
    y1 = _number_or_percentage(grad_el.attrib.get("y1", "0%"), height)
    x2 = _number_or_percentage(grad_el.attrib.get("x2", "100%"), width)
    y2 = _number_or_percentage(grad_el.attrib.get("y2", "0%"), height)

    p0 = Point(x1, y1)
    p1 = Point(x2, y2)

    # compute the vector n perpendicular to vector v from P1 to P0
    v = p0 - p1
    n = v.perpendicular()

    transform = _get_gradient_transform(grad_el, shape_bbox, view_box, upem)

    # apply transformations to points and perpendicular vector
    p0 = transform.map_point(p0)
    p1 = transform.map_point(p1)
    n = transform.map_vector(n)

    # P2 is equal to P1 translated by the orthogonal projection of the transformed
    # vector v' (from P1' to P0') onto the transformed vector n'; before the
    # transform the vector n is perpendicular to v, so the projection of v onto n
    # is zero and P2 == P1; if the transform has a skew or a scale that doesn't
    # preserve aspect ratio, the projection of v' onto n' is non-zero and P2 != P1
    v = p0 - p1
    p2 = p1 + v.projection(n)

    return {"p0": p0, "p1": p1, "p2": p2}


def _parse_radial_gradient(grad_el, shape_bbox, view_box, upem):
    width, height = _get_gradient_units_relative_scale(grad_el, view_box)

    cx = _number_or_percentage(grad_el.attrib.get("cx", "50%"), width)
    cy = _number_or_percentage(grad_el.attrib.get("cy", "50%"), height)
    r = _number_or_percentage(grad_el.attrib.get("r", "50%"), width)

    raw_fx = grad_el.attrib.get("fx")
    fx = _number_or_percentage(raw_fx, width) if raw_fx is not None else cx
    raw_fy = grad_el.attrib.get("fy")
    fy = _number_or_percentage(raw_fy, height) if raw_fy is not None else cy
    fr = _number_or_percentage(grad_el.attrib.get("fr", "0%"), width)

    c0 = Point(fx, fy)
    r0 = fr
    c1 = Point(cx, cy)
    r1 = r

    transform = _get_gradient_transform(grad_el, shape_bbox, view_box, upem)

    # The optional Affine2x2 matrix of COLRv1.RadialGradient is used to transform
    # the circles into ellipses "around their centres": i.e. centres coordinates
    # are _not_ transformed by it. Thus we apply the full transform to them.
    c0 = transform.map_point(c0)
    c1 = transform.map_point(c1)

    # As for the circle radii (which are affected by Affine2x2), we only scale them
    # by the largest between the horizontal and vertical (absolute) scale.
    # Then in Affine2x2 we only store a "fraction" of the original transform, i.e.
    # multiplied by the inverse of the scale that we've already applied to the radii.
    # Especially when gradientUnits="objectBoundingBox", where circle positions and
    # radii are expressed using small floats in the range [0..1], this pre-scaling
    # helps reducing the inevitable rounding errors that arise from storing these
    # values as integers in COLRv1 tables.
    s = max(abs(transform.a), abs(transform.d))
    assert s != 0

    rscale = Affine2D(s, 0, 0, s, 0, 0)
    r0 = rscale.map_vector((r0, 0)).x
    r1 = rscale.map_vector((r1, 0)).x

    affine2x2 = transform.concat(rscale.inverse())

    return {
        "c0": c0,
        "c1": c1,
        "r0": r0,
        "r1": r1,
        "affine2x2": (
            affine2x2[:4] if affine2x2 != Affine2D.identity() else None
        ),
    }


_GRADIENT_INFO = {
    "linearGradient": (PaintLinearGradient, _parse_linear_gradient),
    "radialGradient": (PaintRadialGradient, _parse_radial_gradient),
}


def _color_stop(stop_el):
    offset = _number_or_percentage(stop_el.attrib.get("offset", "0"))
    color = stop_el.attrib.get("stop-color", "black")
    if "stop-opacity" in stop_el.attrib:
        raise ValueError("<stop stop-opacity/> not supported")
    return ColorStop(stopOffset=offset, color=Color.fromstring(color))


def _common_gradient_parts(el):
    spread_method = el.attrib.get("spreadMethod", "pad").upper()
    if spread_method not in Extend.__members__:
        raise ValueError(f"Unknown spreadMethod {spread_method}")

    return {
        "extend": Extend.__members__[spread_method],
        "stops": tuple(_color_stop(stop) for stop in el),
    }


def _paint(nsvg, shape, upem):
    if shape.fill.startswith("url("):
        el = nsvg.resolve_url(shape.fill, "*")

        grad_type, grad_type_parser = _GRADIENT_INFO[etree.QName(el).localname]
        grad_args = _common_gradient_parts(el)
        grad_args.update(
            grad_type_parser(
                el, shape.bounding_box(nsvg.tolerance), nsvg.view_box(), upem
            )
        )
        return grad_type(**grad_args)

    return PaintSolid(color=Color.fromstring(shape.fill, alpha=shape.opacity))


class ColorGlyph(
    collections.namedtuple(
        "ColorGlyph",
        ["ufo", "filename", "glyph_name", "glyph_id", "codepoints", "nsvg"],
    )
):
    @staticmethod
    def create(ufo, filename, glyph_id, codepoints, nsvg):
        logging.info(" ColorGlyph for %s (%s)", filename, codepoints)
        glyph_name = glyph.glyph_name(codepoints)
        base_glyph = ufo.newGlyph(glyph_name)
        base_glyph.width = ufo.info.unitsPerEm

        # Setup direct access to the glyph if possible
        if len(codepoints) == 1:
            base_glyph.unicode = next(iter(codepoints))

        # Grab the transform + (color, glyph) layers for COLR
        return ColorGlyph(ufo, filename, glyph_name, glyph_id, codepoints, nsvg)

    def transform_for_font_space(self):
        """Creates a Transform to map SVG coords to font coords"""
        view_box = self.nsvg.view_box()
        if view_box is None:
            logging.warning(
                f"{self.ufo.info.familyName} has no viewBox; no transform will be applied"
            )
            return Affine2D.identity()
        return _map_viewbox_to_emsquare(view_box, self.ufo.info.unitsPerEm)

    def as_painted_layers(self):
        """Yields (Paint, SVGPath) tuples to draw nsvg."""
        for shape in self.nsvg.shapes():
            yield (_paint(self.nsvg, shape, self.ufo.info.unitsPerEm), shape)

    def paints(self):
        """Set of Paint used by this glyph."""
        return {paint for paint, _ in self.as_painted_layers()}

    def colors(self):
        """Set of Color used by this glyph."""
        return set(chain.from_iterable([p.colors() for p in self.paints()]))
