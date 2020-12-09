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
from itertools import chain, groupby
from lxml import etree  # type: ignore
from nanoemoji.colors import Color
from nanoemoji.config import FontConfig
from nanoemoji import glyph
from nanoemoji.paint import (
    Extend,
    ColorStop,
    Paint,
    PaintLinearGradient,
    PaintRadialGradient,
    PaintSolid,
    PaintTransform,
)
from picosvg.geometric_types import Point, Rect
from picosvg.svg_meta import number_or_percentage
from picosvg.svg_reuse import normalize, affine_between
from picosvg.svg_transform import Affine2D
from picosvg.svg import SVG
from picosvg.svg_types import SVGPath, SVGLinearGradient, SVGRadialGradient
from typing import Generator, NamedTuple, Optional, Sequence, Tuple
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


def _parse_linear_gradient(grad_el, shape_bbox, view_box, upem, shape_opacity=1.0):
    gradient = SVGLinearGradient.from_element(grad_el, view_box)

    p0 = Point(gradient.x1, gradient.y1)
    p1 = Point(gradient.x2, gradient.y2)

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

    common_args = _common_gradient_parts(grad_el, shape_opacity)
    return PaintLinearGradient(  # pytype: disable=wrong-arg-types
        p0=p0, p1=p1, p2=p2, **common_args
    )


def _parse_radial_gradient(grad_el, shape_bbox, view_box, upem, shape_opacity=1.0):
    gradient = SVGRadialGradient.from_element(grad_el, view_box)

    c0 = Point(gradient.fx, gradient.fy)
    r0 = gradient.fr
    c1 = Point(gradient.cx, gradient.cy)
    r1 = gradient.r

    transform = map_viewbox_to_font_emsquare(view_box, upem)

    gradient_units = grad_el.attrib.get("gradientUnits", "objectBoundingBox")
    if gradient_units == "objectBoundingBox":
        bbox_space = Rect(0, 0, 1, 1)
        bbox_transform = Affine2D.rect_to_rect(bbox_space, shape_bbox)
        transform = Affine2D.product(bbox_transform, transform)

    assert transform[1:3] == (0, 0), (
        f"{transform} contains unexpected skew/rotation:"
        " upem, view_box, shape_bbox are all rectangles"
    )

    # if viewBox is not square or if gradientUnits="objectBoundingBox" and the bbox
    # is not square, we may end up with scaleX != scaleY; CORLv1 PaintRadialGradient
    # by themselves can only define circles, not ellipses. We want to keep aspect ratio
    # by applying a uniform scale to the circles, so we use the max (in absolute terms)
    # of scaleX or scaleY.  We will then concatenate any remaining non-proportional
    # transformation with the gradientTransform, and encode the latter as a COLRv1
    # PaintTransform that wraps the PaintRadialGradient (see further below).
    sx, sy = transform.getscale()
    s = max(abs(sx), abs(sy))
    sx = -s if sx < 0 else s
    sy = -s if sy < 0 else s
    proportional_transform = Affine2D(sx, 0, 0, sy, *transform.gettranslate())

    c0 = proportional_transform.map_point(c0)
    c1 = proportional_transform.map_point(c1)
    r0 *= s
    r1 *= s

    gradient_args = {"c0": c0, "c1": c1, "r0": r0, "r1": r1}
    gradient_args.update(_common_gradient_parts(grad_el, shape_opacity))

    gradient_transform = gradient.gradientTransform

    # TODO handle degenerate cases, fallback to solid, w/e

    if (
        proportional_transform == transform
        and gradient_transform == Affine2D.identity()
    ):
        # If the chain of trasforms applied so far ([bbox-to-]vbox-to-upem) maintains the
        # circles' aspect ratio and we don't have any additional gradientTransform, we
        # are done
        return PaintRadialGradient(**gradient_args)  # pytype: disable=wrong-arg-types
    else:
        # Otherwise we need to wrap our PaintRadialGradient in a PaintTransform.
        # To compute the final transform, we first "undo" the transform that we have
        # already applied to the circles (to restore their original coordinate system);
        # then we can apply the SVG gradientTransform (if any), and finally the rest of
        # the transforms. The order matters.
        gradient_transform = Affine2D.product(
            proportional_transform.inverse(),
            Affine2D.product(gradient_transform, transform),
        )
        return PaintTransform(
            gradient_transform,
            PaintRadialGradient(**gradient_args),  # pytype: disable=wrong-arg-types
        )


_GRADIENT_INFO = {
    "linearGradient": _parse_linear_gradient,
    "radialGradient": _parse_radial_gradient,
}


def _color_stop(stop_el, shape_opacity=1.0) -> ColorStop:
    offset = number_or_percentage(stop_el.attrib.get("offset", "0"))
    color = Color.fromstring(stop_el.attrib.get("stop-color", "black"))
    opacity = number_or_percentage(stop_el.attrib.get("stop-opacity", "1"))
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
    path: str  # path.d
    reuses: Tuple[Affine2D, ...] = ()

    def shape_cache_key(self):
        # a hashable cache key ignoring paint
        return (self.path, self.reuses)


def _paint(debug_hint, upem, picosvg, shape):
    if shape.fill.startswith("url("):
        el = picosvg.resolve_url(shape.fill, "*")
        try:
            return _GRADIENT_INFO[etree.QName(el).localname](
                el,
                shape.bounding_box(),
                picosvg.view_box(),
                upem,
                shape.opacity,
            )
        except ValueError as e:
            raise ValueError(
                f"parse failed for {debug_hint}, {etree.tostring(el)[:128]}"
            ) from e

    return PaintSolid(color=Color.fromstring(shape.fill, alpha=shape.opacity))


def _in_glyph_reuse_key(
    debug_hint: str, upem: int, picosvg: SVG, shape: SVGPath, reuse_tolerance: float
) -> Tuple[Paint, SVGPath]:
    """Within a glyph reuse shapes only when painted consistently.
    paint+normalized shape ensures this."""
    return (
        _paint(debug_hint, upem, picosvg, shape),
        normalize(shape, reuse_tolerance),
    )


def _painted_layers(
    debug_hint: str,
    upem: int,
    picosvg: SVG,
    reuse_tolerance: float,
    ignore_reuse_error: bool = True,
) -> Generator[PaintedLayer, None, None]:
    if reuse_tolerance < 0:
        # shape reuse disabled
        for path in picosvg.shapes():
            yield PaintedLayer(_paint(debug_hint, upem, picosvg, path), path.d)
        return

    # Don't sort; we only want to find groups that are consecutive in the picosvg
    # to ensure we don't mess up layer order
    for (paint, normalized), paths in groupby(
        picosvg.shapes(),
        key=lambda s: _in_glyph_reuse_key(
            debug_hint, upem, picosvg, s, reuse_tolerance
        ),
    ):
        paths = list(paths)
        transforms = ()
        if len(paths) > 1:
            transforms = tuple(
                affine_between(paths[0], p, reuse_tolerance) for p in paths[1:]
            )

        success = True
        for path, transform in zip(paths[1:], transforms):
            if transform is None:
                success = False
                error_msg = (
                    f"{debug_hint} grouped the following paths but no affine_between "
                    f"could be computed:\n  {paths[0]}\n  {path}"
                )
                if ignore_reuse_error:
                    logging.warning(error_msg)
                else:
                    raise ValueError(error_msg)

        if success:
            yield PaintedLayer(paint, paths[0].d, transforms)
        else:
            for path in paths:
                yield PaintedLayer(paint, path.d)


class ColorGlyph(NamedTuple):
    ufo: ufoLib2.Font
    filename: str
    glyph_name: str
    glyph_id: int
    codepoints: Tuple[int, ...]
    painted_layers: Optional[Tuple[PaintedLayer, ...]]  # None for untouched formats
    svg: SVG  # picosvg except for untouched formats

    @staticmethod
    def create(
        font_config: FontConfig,
        ufo: ufoLib2.Font,
        filename: str,
        glyph_id: int,
        codepoints: Tuple[int],
        svg: SVG,
    ):
        logging.debug(" ColorGlyph for %s (%s)", filename, codepoints)
        glyph_name = glyph.glyph_name(codepoints)
        base_glyph = ufo.newGlyph(glyph_name)
        base_glyph.width = ufo.info.unitsPerEm

        # Setup direct access to the glyph if possible
        if len(codepoints) == 1:
            base_glyph.unicode = next(iter(codepoints))

        # Grab the transform + (color, glyph) layers unless they aren't to be touched
        painted_layers = None
        if font_config.has_picosvgs:
            painted_layers = tuple(
                _painted_layers(
                    filename,
                    ufo.info.unitsPerEm,
                    svg,
                    font_config.reuse_tolerance,
                    font_config.ignore_reuse_error,
                )
            )
        return ColorGlyph(
            ufo, filename, glyph_name, glyph_id, codepoints, painted_layers, svg
        )

    def _has_viewbox_for_transform(self) -> bool:
        view_box = self.svg.view_box()
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
            self.svg.view_box(), self.ufo.info.unitsPerEm
        )

    def transform_for_otsvg_space(self):
        """Creates a Transform to map SVG coords OT-SVG coords"""
        if not self._has_viewbox_for_transform():
            return Affine2D.identity()
        return map_viewbox_to_otsvg_emsquare(
            self.svg.view_box(), self.ufo.info.unitsPerEm
        )

    def paints(self):
        """Set of Paint used by this glyph."""
        return {l.paint for l in self.painted_layers}

    def colors(self):
        """Set of Color used by this glyph."""
        return set(chain.from_iterable([p.colors() for p in self.paints()]))
