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
from itertools import chain, groupby
from lxml import etree  # type: ignore
from nanoemoji.colors import Color
from nanoemoji import glyph
from nanoemoji.paint import (
    Extend,
    ColorStop,
    Paint,
    PaintLinearGradient,
    PaintRadialGradient,
    PaintSolid,
)
from picosvg.geometric_types import Point, Rect
from picosvg.svg_reuse import normalize, affine_between
from picosvg.svg_transform import Affine2D
from picosvg.svg import SVG
from picosvg.svg_types import SVGPath
from typing import Generator, Mapping, NamedTuple, Tuple
import ufoLib2


def _scale_viewbox_to_emsquare(view_box: Rect, upem: int) -> Tuple[float, float]:
    # scale to font upem
    return (upem / view_box.w, upem / view_box.h)


def _shift_origin_0_0(
    view_box: Rect, x_scale: float, y_scale: float
) -> Tuple[float, float]:
    # shift so origin is 0,0
    return (-view_box.x * x_scale, -view_box.y * y_scale)


def map_viewbox_to_font_emsquare(view_box: Rect, upem: int) -> Affine2D:
    x_scale, y_scale = _scale_viewbox_to_emsquare(view_box, upem)
    # flip y axis
    y_scale = -y_scale
    # shift so things are in the right place
    dx, dy = _shift_origin_0_0(view_box, x_scale, y_scale)
    dy = dy + upem
    return Affine2D(x_scale, 0, 0, y_scale, dx, dy)


# https://docs.microsoft.com/en-us/typography/opentype/spec/svg#coordinate-systems-and-glyph-metrics
def map_viewbox_to_otsvg_emsquare(view_box: Rect, upem: int) -> Affine2D:
    x_scale, y_scale = _scale_viewbox_to_emsquare(view_box, upem)
    dx, dy = _shift_origin_0_0(view_box, x_scale, y_scale)

    # shift so things are in the right place
    dy = dy - upem
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


def _get_gradient_transform(grad_el, shape_bbox, view_box, upem) -> Affine2D:
    transform = map_viewbox_to_font_emsquare(view_box, upem)

    gradient_units = grad_el.attrib.get("gradientUnits", "objectBoundingBox")
    if gradient_units == "objectBoundingBox":
        bbox_space = Rect(0, 0, 1, 1)
        bbox_transform = Affine2D.rect_to_rect(bbox_space, shape_bbox)
        transform = Affine2D.product(bbox_transform, transform)

    if "gradientTransform" in grad_el.attrib:
        gradient_transform = Affine2D.fromstring(grad_el.attrib["gradientTransform"])
        transform = Affine2D.product(gradient_transform, transform)

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
    # by the maximum of the (absolute) scale or skew.
    # Then in Affine2x2 we only store a "fraction" of the original transform, i.e.
    # multiplied by the inverse of the scale that we've already applied to the radii.
    # Especially when gradientUnits="objectBoundingBox", where circle positions and
    # radii are expressed using small floats in the range [0..1], this pre-scaling
    # helps reducing the inevitable rounding errors that arise from storing these
    # values as integers in COLRv1 tables.
    s = max(abs(v) for v in transform[:4])

    rscale = Affine2D(s, 0, 0, s, 0, 0)
    r0 = rscale.map_vector((r0, 0)).x
    r1 = rscale.map_vector((r1, 0)).x

    affine2x2 = Affine2D.product(rscale.inverse(), transform)

    gradient = {
        "c0": c0,
        "c1": c1,
        "r0": r0,
        "r1": r1,
        "affine2x2": (affine2x2[:4] if affine2x2 != Affine2D.identity() else None),
    }

    # TODO handle degenerate cases, fallback to solid, w/e

    return gradient


_GRADIENT_INFO = {
    "linearGradient": (PaintLinearGradient, _parse_linear_gradient),
    "radialGradient": (PaintRadialGradient, _parse_radial_gradient),
}


def _color_stop(stop_el, shape_opacity=1.0) -> ColorStop:
    offset = _number_or_percentage(stop_el.attrib.get("offset", "0"))
    color = Color.fromstring(stop_el.attrib.get("stop-color", "black"))
    opacity = _number_or_percentage(stop_el.attrib.get("stop-opacity", "1"))
    color = color._replace(alpha=color.alpha * opacity * shape_opacity)
    return ColorStop(stopOffset=offset, color=color)


def _common_gradient_parts(el, shape_opacity=1.0):
    spread_method = el.attrib.get("spreadMethod", "pad").upper()
    if spread_method not in Extend.__members__:
        raise ValueError(f"Unknown spreadMethod {spread_method}")

    return {
        "extend": Extend.__members__[spread_method],
        "stops": tuple(_color_stop(stop, shape_opacity) for stop in el),
    }


class PaintedLayer(NamedTuple):
    paint: Paint
    path: SVGPath
    reuses: Tuple[Affine2D]


class ColorGlyph(NamedTuple):
    ufo: ufoLib2.Font
    filename: str
    glyph_name: str
    glyph_id: int
    codepoints: Tuple[int, ...]
    picosvg: SVG

    def _paint(self, shape):
        upem = self.ufo.info.unitsPerEm
        if shape.fill.startswith("url("):
            el = self.picosvg.resolve_url(shape.fill, "*")

            grad_type, grad_type_parser = _GRADIENT_INFO[etree.QName(el).localname]
            grad_args = _common_gradient_parts(el, shape.opacity)
            try:
                grad_args.update(
                    grad_type_parser(
                        el, shape.bounding_box(), self.picosvg.view_box(), upem
                    )
                )
            except ValueError as e:
                raise ValueError(
                    f"parse failed for {self.filename}, {etree.tostring(el)[:128]}"
                ) from e
            return grad_type(**grad_args)

        return PaintSolid(color=Color.fromstring(shape.fill, alpha=shape.opacity))

    def _in_glyph_reuse_key(self, shape: SVGPath) -> Tuple[Paint, SVGPath]:
        """Within a glyph reuse shapes only when painted consistently.

        paint+normalized shape ensures this."""
        return (self._paint(shape), normalize(shape))

    @staticmethod
    def create(ufo, filename, glyph_id, codepoints, picosvg):
        logging.debug(" ColorGlyph for %s (%s)", filename, codepoints)
        glyph_name = glyph.glyph_name(codepoints)
        base_glyph = ufo.newGlyph(glyph_name)
        base_glyph.width = ufo.info.unitsPerEm

        # Setup direct access to the glyph if possible
        if len(codepoints) == 1:
            base_glyph.unicode = next(iter(codepoints))

        # Grab the transform + (color, glyph) layers for COLR
        return ColorGlyph(ufo, filename, glyph_name, glyph_id, codepoints, picosvg)

    def _has_viewbox_for_transform(self) -> bool:
        view_box = self.picosvg.view_box()
        if view_box is None:
            logging.warning(
                f"{self.ufo.info.familyName} has no viewBox; no transform will be applied"
            )
        return view_box is not None

    def transform_for_font_space(self):
        """Creates a Transform to map SVG coords to font coords"""
        if not self._has_viewbox_for_transform():
            return Affine2D.identity()
        return map_viewbox_to_font_emsquare(
            self.picosvg.view_box(), self.ufo.info.unitsPerEm
        )

    def transform_for_otsvg_space(self):
        """Creates a Transform to map SVG coords OT-SVG coords"""
        if not self._has_viewbox_for_transform():
            return Affine2D.identity()
        return map_viewbox_to_otsvg_emsquare(
            self.picosvg.view_box(), self.ufo.info.unitsPerEm
        )

    def as_painted_layers(self) -> Generator[PaintedLayer, None, None]:
        # Don't sort; we only want to find groups that are consecutive in the picosvg
        # to ensure we don't mess up layer order
        for (paint, normalized), paths in groupby(
            self.picosvg.shapes(), key=self._in_glyph_reuse_key
        ):
            paths = list(paths)
            transforms = ()
            if len(paths) > 1:
                transforms = tuple(affine_between(paths[0], p) for p in paths[1:])
            for path, transform in zip(paths[1:], transforms):
                if transform is None:
                    raise ValueError(
                        f"{self.filename} grouped {paths[0]} and {path} but no affine_between could be computed"
                    )
            yield PaintedLayer(paint, paths[0], transforms)

    def paints(self):
        """Set of Paint used by this glyph."""
        return {l.paint for l in self.as_painted_layers()}

    def colors(self):
        """Set of Color used by this glyph."""
        return set(chain.from_iterable([p.colors() for p in self.paints()]))
