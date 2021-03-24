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

import math
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


def _scale_viewbox_to_font_metrics(
    view_box: Rect, ascender: int, descender: int, width: int
):
    assert descender <= 0
    # scale height to (ascender - descender)
    scale = (ascender - descender) / view_box.h
    # shift so width is centered
    dx = (width - scale * view_box.w) / 2
    return Affine2D.compose_ltr(
        (
            # first normalize viewbox origin
            Affine2D(1, 0, 0, 1, -view_box.x, -view_box.y),
            Affine2D(scale, 0, 0, scale, dx, 0),
        )
    )


def map_viewbox_to_font_space(
    view_box: Rect, ascender: int, descender: int, width: int, user_transform: Affine2D
) -> Affine2D:
    return Affine2D.compose_ltr(
        [
            _scale_viewbox_to_font_metrics(view_box, ascender, descender, width),
            # flip y axis and shift so things are in the right place
            Affine2D(1, 0, 0, -1, 0, ascender),
            user_transform,
        ]
    )


# https://docs.microsoft.com/en-us/typography/opentype/spec/svg#coordinate-systems-and-glyph-metrics
def map_viewbox_to_otsvg_space(
    view_box: Rect, ascender: int, descender: int, width: int, user_transform: Affine2D
) -> Affine2D:
    return Affine2D.compose_ltr(
        [
            _scale_viewbox_to_font_metrics(view_box, ascender, descender, width),
            # shift things in the [+x,-y] quadrant where OT-SVG expects them
            Affine2D(1, 0, 0, 1, 0, -ascender),
            user_transform,
        ]
    )


def _get_gradient_transform(
    config: FontConfig,
    grad_el: etree.Element,
    shape_bbox: Rect,
    view_box: Rect,
    glyph_width: int,
) -> Affine2D:
    transform = map_viewbox_to_font_space(
        view_box, config.ascender, config.descender, glyph_width, config.transform
    )

    gradient_units = grad_el.attrib.get("gradientUnits", "objectBoundingBox")
    if gradient_units == "objectBoundingBox":
        bbox_space = Rect(0, 0, 1, 1)
        bbox_transform = Affine2D.rect_to_rect(bbox_space, shape_bbox)
        transform = Affine2D.product(bbox_transform, transform)

    if "gradientTransform" in grad_el.attrib:
        gradient_transform = Affine2D.fromstring(grad_el.attrib["gradientTransform"])
        transform = Affine2D.product(gradient_transform, transform)

    return transform


def _parse_linear_gradient(
    config: FontConfig,
    grad_el: etree.Element,
    shape_bbox: Rect,
    view_box: Rect,
    glyph_width: int,
    shape_opacity: float = 1.0,
):
    gradient = SVGLinearGradient.from_element(grad_el, view_box)

    p0 = Point(gradient.x1, gradient.y1)
    p1 = Point(gradient.x2, gradient.y2)

    # Set P2 to P1 rotated 90 degrees counter-clockwise around P0
    p2 = p0 + (p1 - p0).perpendicular()

    transform = _get_gradient_transform(
        config, grad_el, shape_bbox, view_box, glyph_width
    )

    p0 = transform.map_point(p0)
    p1 = transform.map_point(p1)
    p2 = transform.map_point(p2)

    common_args = _common_gradient_parts(grad_el, shape_opacity)
    return PaintLinearGradient(  # pytype: disable=wrong-arg-types
        p0=p0, p1=p1, p2=p2, **common_args
    )


def _decompose_uniform_transform(transform: Affine2D) -> Tuple[Affine2D, Affine2D]:
    scale, remaining_transform = transform.decompose_scale()
    s = max(*scale.getscale())
    # most transforms will contain a Y-flip component as result of mapping from SVG to
    # font coordinate space. Here we keep this negative Y sign as part of the uniform
    # transform since it does not affect the circle-ness, and also makes so that the
    # font-mapped gradient geometry is more likely to be in the +x,+y quadrant like
    # the path geometry it is applied to.
    uniform_scale = Affine2D(s, 0, 0, math.copysign(s, transform.d), 0, 0)
    remaining_transform = Affine2D.compose_ltr(
        (uniform_scale.inverse(), scale, remaining_transform)
    )

    translate, remaining_transform = remaining_transform.decompose_translation()
    # round away very small float-math noise, so we get clean 0s and 1s for the special
    # case of identity matrix which implies no wrapping PaintTransform
    remaining_transform = remaining_transform.round(9)

    logging.debug(
        "Decomposing %r:\n\tscale: %r\n\ttranslate: %r\n\tremaining: %r",
        transform,
        uniform_scale,
        translate,
        remaining_transform,
    )

    uniform_transform = Affine2D.compose_ltr((uniform_scale, translate))
    return uniform_transform, remaining_transform


def _parse_radial_gradient(
    config: FontConfig,
    grad_el: etree.Element,
    shape_bbox: Rect,
    view_box: Rect,
    glyph_width: int,
    shape_opacity: float = 1.0,
):
    gradient = SVGRadialGradient.from_element(grad_el, view_box)

    c0 = Point(gradient.fx, gradient.fy)
    r0 = gradient.fr
    c1 = Point(gradient.cx, gradient.cy)
    r1 = gradient.r

    transform = _get_gradient_transform(
        config, grad_el, shape_bbox, view_box, glyph_width
    )

    # if gradientUnits="objectBoundingBox" and the bbox is not square, or there's some
    # gradientTransform, we may end up with a transformation that does not keep the
    # aspect ratio of the gradient circles and turns them into ellipses, but CORLv1
    # PaintRadialGradient by itself can only define circles. Thus we only apply the
    # uniform scale and translate components of the original transform to the circles,
    # then encode any remaining non-uniform transformation as a COLRv1 PaintTransform
    # that wraps the PaintRadialGradient (see further below).
    uniform_transform, remaining_transform = _decompose_uniform_transform(transform)

    c0 = uniform_transform.map_point(c0)
    c1 = uniform_transform.map_point(c1)

    sx, _ = uniform_transform.getscale()
    r0 *= sx
    r1 *= sx

    gradient_args = {"c0": c0, "c1": c1, "r0": r0, "r1": r1}
    gradient_args.update(_common_gradient_parts(grad_el, shape_opacity))

    # TODO handle degenerate cases, fallback to solid, w/e

    if remaining_transform == Affine2D.identity():
        # If the chain of trasforms applied so far maintains the circles' aspect ratio
        # we are done
        return PaintRadialGradient(**gradient_args)  # pytype: disable=wrong-arg-types
    else:
        # Otherwise we need to wrap our PaintRadialGradient in a PaintTransform.
        return PaintTransform(
            remaining_transform,
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


def _paint(
    debug_hint: str, config: FontConfig, picosvg: SVG, shape: SVGPath, glyph_width: int
) -> Paint:
    if shape.fill.startswith("url("):
        el = picosvg.resolve_url(shape.fill, "*")
        try:
            return _GRADIENT_INFO[etree.QName(el).localname](
                config,
                el,
                shape.bounding_box(),
                picosvg.view_box(),
                glyph_width,
                shape.opacity,
            )
        except ValueError as e:
            raise ValueError(
                f"parse failed for {debug_hint}, {etree.tostring(el)[:128]}"
            ) from e

    return PaintSolid(color=Color.fromstring(shape.fill, alpha=shape.opacity))


def _in_glyph_reuse_key(
    debug_hint: str, config: FontConfig, picosvg: SVG, shape: SVGPath, glyph_width: int
) -> Tuple[Paint, SVGPath]:
    """Within a glyph reuse shapes only when painted consistently.
    paint+normalized shape ensures this."""
    return (
        _paint(debug_hint, config, picosvg, shape, glyph_width),
        normalize(shape, config.reuse_tolerance),
    )


def _painted_layers(
    debug_hint: str,
    config: FontConfig,
    picosvg: SVG,
    glyph_width: int,
) -> Generator[PaintedLayer, None, None]:
    if config.reuse_tolerance < 0:
        # shape reuse disabled
        for path in picosvg.shapes():
            yield PaintedLayer(
                _paint(debug_hint, config, picosvg, path, glyph_width), path.d
            )
        return

    # Don't sort; we only want to find groups that are consecutive in the picosvg
    # to ensure we don't mess up layer order
    for (paint, normalized), paths in groupby(
        picosvg.shapes(),
        key=lambda s: _in_glyph_reuse_key(debug_hint, config, picosvg, s, glyph_width),
    ):
        paths = list(paths)
        transforms = ()
        if len(paths) > 1:
            transforms = tuple(
                affine_between(paths[0], p, config.reuse_tolerance) for p in paths[1:]
            )

        success = True
        for path, transform in zip(paths[1:], transforms):
            if transform is None:
                success = False
                error_msg = (
                    f"{debug_hint} grouped the following paths but no affine_between "
                    f"could be computed:\n  {paths[0]}\n  {path}"
                )
                if config.ignore_reuse_error:
                    logging.warning(error_msg)
                else:
                    raise ValueError(error_msg)

        if success:
            yield PaintedLayer(paint, paths[0].d, transforms)
        else:
            for path in paths:
                yield PaintedLayer(paint, path.d)


def _color_glyph_advance_width(view_box: Rect, config: FontConfig) -> int:
    # Scale advance width proportionally to viewbox aspect ratio.
    # Use the default advance width if it's larger than the proportional one.
    font_height = config.ascender - config.descender  # descender <= 0
    return max(config.width, round(font_height * view_box.w / view_box.h))


class ColorGlyph(NamedTuple):
    ufo: ufoLib2.Font
    filename: str
    glyph_name: str
    glyph_id: int
    codepoints: Tuple[int, ...]
    painted_layers: Optional[Tuple[PaintedLayer, ...]]  # None for untouched formats
    svg: SVG  # picosvg except for untouched formats
    user_transform: Affine2D

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

        # non-square aspect ratio == proportional width; square == monospace
        view_box = svg.view_box()
        if view_box is not None:
            base_glyph.width = _color_glyph_advance_width(view_box, font_config)
        else:
            base_glyph.width = font_config.width

        # Setup direct access to the glyph if possible
        if len(codepoints) == 1:
            base_glyph.unicode = next(iter(codepoints))

        # Grab the transform + (color, glyph) layers unless they aren't to be touched
        painted_layers = None
        if font_config.has_picosvgs:
            painted_layers = tuple(
                _painted_layers(
                    filename,
                    font_config,
                    svg,
                    base_glyph.width,
                )
            )

        return ColorGlyph(
            ufo,
            filename,
            glyph_name,
            glyph_id,
            codepoints,
            painted_layers,
            svg,
            font_config.transform,
        )

    def _has_viewbox_for_transform(self) -> bool:
        view_box = self.svg.view_box()
        if view_box is None:
            logging.warning(
                f"{self.ufo.info.familyName} has no viewBox; no transform will be applied"
            )
        return view_box is not None

    def _transform(self, map_fn):
        if not self._has_viewbox_for_transform():
            return Affine2D.identity()
        return map_fn(
            self.svg.view_box(),
            self.ufo.info.ascender,
            self.ufo.info.descender,
            self.ufo[self.glyph_name].width,
            self.user_transform,
        )

    def transform_for_otsvg_space(self):
        return self._transform(map_viewbox_to_otsvg_space)

    def transform_for_font_space(self):
        return self._transform(map_viewbox_to_font_space)

    def paints(self):
        """Set of Paint used by this glyph."""
        return {l.paint for l in self.painted_layers}

    def colors(self):
        """Set of Color used by this glyph."""
        return set(chain.from_iterable([p.colors() for p in self.paints()]))
