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

"""Helpers for expressing paint.

Based on https://github.com/googlefonts/colr-gradients-spec/blob/main/colr-gradients-spec.md#structure-of-gradient-colr-v1-extensions.
"""
import dataclasses
from enum import Enum, IntEnum
from absl import logging
from fontTools.ttLib.tables import otTables as ot
from math import copysign, radians
from nanoemoji.colors import Color
from nanoemoji.fixed import (
    int16_safe,
    f2dot14_safe,
    MIN_INT16,
    MAX_INT16,
    MIN_UINT16,
    MAX_UINT16,
)
from picosvg.geometric_types import Point, almost_equal
from picosvg.svg_transform import Affine2D
from typing import (
    Any,
    ClassVar,
    Generator,
    Iterable,
    Mapping,
    Optional,
    Sequence,
    Tuple,
)


class Extend(Enum):
    PAD = (0,)
    REPEAT = (1,)
    REFLECT = (2,)


# Porter-Duff modes for COLRv1 PaintComposite:
# https://github.com/googlefonts/colr-gradients-spec/tree/off_sub_1#compositemode-enumeration
class CompositeMode(IntEnum):
    CLEAR = 0
    SRC = 1
    DEST = 2
    SRC_OVER = 3
    DEST_OVER = 4
    SRC_IN = 5
    DEST_IN = 6
    SRC_OUT = 7
    DEST_OUT = 8
    SRC_ATOP = 9
    DEST_ATOP = 10
    XOR = 11
    PLUS = 12
    SCREEN = 13
    OVERLAY = 14
    DARKEN = 15
    LIGHTEN = 16
    COLOR_DODGE = 17
    COLOR_BURN = 18
    HARD_LIGHT = 19
    SOFT_LIGHT = 20
    DIFFERENCE = 21
    EXCLUSION = 22
    MULTIPLY = 23
    HSL_HUE = 24
    HSL_SATURATION = 25
    HSL_COLOR = 26
    HSL_LUMINOSITY = 27


def _identity(v):
    return v


_PAINT_FIELD_TO_OT_FIELD = {
    "format": ("PaintFormat", _identity),
    "paint": ("Paint", _identity),
    "transform": ("Transform", lambda t: (t.xx, t.yx, t.xy, t.yy, t.dx, t.dy)),
    "center": (("centerX", "centerY"), _identity),
}


@dataclasses.dataclass(frozen=True)
class PaintTraverseContext:
    path: Tuple["Paint", ...]
    paint: "Paint"
    transform: Affine2D


@dataclasses.dataclass(frozen=True)
class ColorStop:
    stopOffset: float = 0.0
    color: Color = Color.fromstring("black")


@dataclasses.dataclass(frozen=True)
class Paint:
    format: ClassVar[int] = -1  # so pytype knows all Paint have format

    def colors(self) -> Generator[Color, None, None]:
        raise NotImplementedError()

    def to_ufo_paint(self, colors: Sequence[Color]):
        raise NotImplementedError()

    def breadth_first(self) -> Generator[PaintTraverseContext, None, None]:
        frontier = [PaintTraverseContext((), self, Affine2D.identity())]
        while frontier:
            context = frontier.pop(0)
            yield context
            transform = context.transform
            paint_transform = context.paint.gettransform()
            transform = Affine2D.compose_ltr(
                (
                    transform,
                    paint_transform,
                )
            )
            for paint in context.paint.children():
                frontier.append(
                    PaintTraverseContext(
                        context.path + (context.paint,), paint, transform
                    )
                )

    def children(self) -> Iterable["Paint"]:
        return ()

    def gettransform(self) -> Affine2D:
        # Returns the transform caused by this Paint (not it's ancestors)
        return Affine2D.identity()

    @classmethod
    def from_ot(cls, ot_paint: ot.Paint) -> "Paint":
        paint_t = globals()[ot_paint.getFormatName()]
        paint_args = []
        for f in dataclasses.fields(paint_t):
            ot_field, converter = _PAINT_FIELD_TO_OT_FIELD.get(
                f.name, (f.name, _identity)
            )
            if isinstance(ot_field, tuple):
                arg = tuple(converter(getattr(ot_paint, f)) for f in ot_field)
            else:
                arg = converter(getattr(ot_paint, ot_field))
            paint_args.append(arg)
        paint = paint_t(*paint_args)
        return paint


@dataclasses.dataclass(frozen=True)
class PaintColrLayers(Paint):
    format: ClassVar[int] = int(ot.PaintFormat.PaintColrLayers)
    layers: Tuple[Paint, ...]

    def colors(self):
        for p in self.layers:
            yield from p.colors()

    def to_ufo_paint(self, colors):
        return {
            "Format": self.format,
            "Layers": [p.to_ufo_paint(colors) for p in self.layers],
        }

    def children(self):
        return self.layers


@dataclasses.dataclass(frozen=True)
class PaintSolid(Paint):
    format: ClassVar[int] = int(ot.PaintFormat.PaintSolid)
    color: Color = Color.fromstring("black")

    def colors(self):
        yield self.color

    def to_ufo_paint(self, colors):
        return {
            "Format": self.format,
            "PaletteIndex": colors.index(self.color.opaque()),
            "Alpha": self.color.alpha,
        }


def _ufoColorLine(gradient, colors):
    return {
        "ColorStop": [
            {
                "StopOffset": stop.stopOffset,
                "PaletteIndex": colors.index(stop.color.opaque()),
                "Alpha": stop.color.alpha,
            }
            for stop in gradient.stops
        ],
        "Extend": gradient.extend.name.lower(),
    }


@dataclasses.dataclass(frozen=True)
class PaintLinearGradient(Paint):
    format: ClassVar[int] = int(ot.PaintFormat.PaintLinearGradient)
    extend: Extend = Extend.PAD
    stops: Tuple[ColorStop, ...] = tuple()
    p0: Point = Point()
    p1: Point = Point()
    p2: Point = None  # if normal undefined, default to P1 rotated 90° cc'wise

    def __post_init__(self):
        if self.p2 is None:
            p0, p1 = Point(*self.p0), Point(*self.p1)
            # use object.__setattr__ as the dataclass is frozen
            object.__setattr__(self, "p2", p0 + (p1 - p0).perpendicular())

    def colors(self):
        for stop in self.stops:
            yield stop.color

    def to_ufo_paint(self, colors):
        return {
            "Format": self.format,
            "ColorLine": _ufoColorLine(self, colors),
            "x0": self.p0[0],
            "y0": self.p0[1],
            "x1": self.p1[0],
            "y1": self.p1[1],
            "x2": self.p2[0],
            "y2": self.p2[1],
        }

    def check_overflows(self) -> "PaintLinearGradient":
        for i in range(3):
            attr_name = f"p{i}"
            value = getattr(self, attr_name)
            for j in range(2):
                if not (MIN_INT16 <= value[j] <= MAX_INT16):
                    raise OverflowError(
                        f"{self.__class__.__name__}.{attr_name}[{j}] ({value[j]}) is "
                        f"out of bounds: [{MIN_INT16}...{MAX_INT16}]"
                    )
        return self

    def apply_transform(self, transform: Affine2D) -> Paint:
        return dataclasses.replace(
            self,
            p0=transform.map_point(self.p0),
            p1=transform.map_point(self.p1),
            p2=transform.map_point(self.p2),
        ).check_overflows()


def _decompose_uniform_transform(transform: Affine2D) -> Tuple[Affine2D, Affine2D]:
    scale, remaining_transform = transform.decompose_scale()
    s = max(*scale.getscale())
    # most transforms will contain a Y-flip component as result of mapping from SVG to
    # font coordinate space. Here we keep this negative Y sign as part of the uniform
    # transform since it does not affect the circle-ness, and also makes so that the
    # font-mapped gradient geometry is more likely to be in the +x,+y quadrant like
    # the path geometry it is applied to.
    uniform_scale = Affine2D(s, 0, 0, copysign(s, transform.d), 0, 0)
    remaining_transform = Affine2D.compose_ltr(
        (uniform_scale.inverse(), scale, remaining_transform)
    )

    translate, remaining_transform = remaining_transform.decompose_translation()
    # round away very small float-math noise, so we get clean 0s and 1s for the special
    # case of identity matrix which implies no wrapping transform
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


@dataclasses.dataclass(frozen=True)
class PaintRadialGradient(Paint):
    format: ClassVar[int] = int(ot.PaintFormat.PaintRadialGradient)
    extend: Extend = Extend.PAD
    stops: Tuple[ColorStop, ...] = tuple()
    c0: Point = Point()
    c1: Point = Point()
    r0: float = 0.0
    r1: float = 0.0

    def colors(self):
        for stop in self.stops:
            yield stop.color

    def to_ufo_paint(self, colors):
        paint = {
            "Format": self.format,
            "ColorLine": _ufoColorLine(self, colors),
            "x0": self.c0[0],
            "y0": self.c0[1],
            "r0": self.r0,
            "x1": self.c1[0],
            "y1": self.c1[1],
            "r1": self.r1,
        }
        return paint

    def check_overflows(self) -> "PaintRadialGradient":
        int_bounds = {
            "c": (MIN_INT16, MAX_INT16),
            "r": (MIN_UINT16, MAX_UINT16),
        }
        attrs = []
        for prefix in ("c", "r"):
            for i in range(2):
                attr_name = f"{prefix}{i}"
                value = getattr(self, attr_name)
                if prefix == "c":
                    attrs.extend((f"{attr_name}[{j}]", value[j]) for j in range(2))
                else:
                    attrs.append((f"{attr_name}", value))
        for attr_name, value in attrs:
            min_value, max_value = int_bounds[attr_name[0]]
            if not (min_value <= value <= max_value):
                raise OverflowError(
                    f"{self.__class__.__name__}.{attr_name} ({value}) is "
                    f"out of bounds: [{min_value}...{max_value}]"
                )
        return self

    def apply_transform(self, transform: Affine2D) -> Paint:
        # if gradientUnits="objectBoundingBox" and the bbox is not square, or there's some
        # gradientTransform, we may end up with a transformation that does not keep the
        # aspect ratio of the gradient circles and turns them into ellipses, but CORLv1
        # PaintRadialGradient by itself can only define circles. Thus we only apply the
        # uniform scale and translate components of the original transform to the circles,
        # then encode any remaining non-uniform transformation as a COLRv1 transform
        # that wraps the PaintRadialGradient (see further below).
        uniform_transform, remaining_transform = _decompose_uniform_transform(transform)

        c0 = uniform_transform.map_point(self.c0)
        c1 = uniform_transform.map_point(self.c1)

        sx, _ = uniform_transform.getscale()
        r0 = self.r0 * sx
        r1 = self.r1 * sx

        # TODO handle degenerate cases, fallback to solid, w/e
        return transformed(
            remaining_transform,
            dataclasses.replace(self, c0=c0, c1=c1, r0=r0, r1=r1).check_overflows(),
        )


# TODO PaintSweepGradient


@dataclasses.dataclass(frozen=True)
class PaintGlyph(Paint):
    format: ClassVar[int] = int(ot.PaintFormat.PaintGlyph)
    glyph: str
    paint: Paint

    def colors(self):
        yield from self.paint.colors()

    def to_ufo_paint(self, colors):
        paint = {
            "Format": self.format,
            "Glyph": self.glyph,
            "Paint": self.paint.to_ufo_paint(colors),
        }
        return paint

    def children(self) -> Iterable[Paint]:
        return (self.paint,)


@dataclasses.dataclass(frozen=True)
class PaintColrGlyph(Paint):
    format: ClassVar[int] = int(ot.PaintFormat.PaintColrGlyph)
    glyph: str

    def to_ufo_paint(self, _):
        paint = {"Format": self.format, "Glyph": self.glyph}
        return paint


@dataclasses.dataclass(frozen=True)
class PaintTransform(Paint):
    format: ClassVar[int] = int(ot.PaintFormat.PaintTransform)
    transform: Tuple[float, float, float, float, float, float]
    paint: Paint

    def colors(self):
        yield from self.paint.colors()

    def to_ufo_paint(self, colors):
        paint = {
            "Format": self.format,
            "Transform": self.transform,
            "Paint": self.paint.to_ufo_paint(colors),
        }
        return paint

    def children(self) -> Iterable[Paint]:
        return (self.paint,)

    def gettransform(self) -> Affine2D:
        return Affine2D(*self.transform)


@dataclasses.dataclass(frozen=True)
class PaintTranslate(Paint):
    format: ClassVar[int] = int(ot.PaintFormat.PaintTranslate)
    paint: Paint
    dx: int
    dy: int

    def colors(self):
        yield from self.paint.colors()

    def to_ufo_paint(self, colors):
        paint = {
            "Format": self.format,
            "Paint": self.paint.to_ufo_paint(colors),
            "dx": self.dx,
            "dy": self.dy,
        }
        return paint

    def children(self) -> Iterable[Paint]:
        return (self.paint,)

    def gettransform(self) -> Affine2D:
        return Affine2D.identity().translate(self.dx, self.dy)


@dataclasses.dataclass(frozen=True)
class PaintScale(Paint):
    format: ClassVar[int] = int(ot.PaintFormat.PaintScale)
    paint: Paint
    scaleX: float = 1.0
    scaleY: float = 1.0

    def colors(self):
        yield from self.paint.colors()

    def to_ufo_paint(self, colors):
        paint = {
            "Format": self.format,
            "Paint": self.paint.to_ufo_paint(colors),
            "scaleX": self.scaleX,
            "scaleY": self.scaleY,
        }
        return paint

    def children(self) -> Iterable[Paint]:
        return (self.paint,)

    def gettransform(self) -> Affine2D:
        return Affine2D.identity().scale(self.scaleX, self.scaleY)


@dataclasses.dataclass(frozen=True)
class PaintScaleAroundCenter(Paint):
    format: ClassVar[int] = int(ot.PaintFormat.PaintScaleAroundCenter)
    paint: Paint
    scaleX: float = 1.0
    scaleY: float = 1.0
    center: Point = Point()

    def colors(self):
        yield from self.paint.colors()

    def to_ufo_paint(self, colors):
        paint = {
            "Format": self.format,
            "Paint": self.paint.to_ufo_paint(colors),
            "scaleX": self.scaleX,
            "scaleY": self.scaleY,
            "centerX": self.center[0],
            "centerY": self.center[1],
        }
        return paint

    def children(self) -> Iterable[Paint]:
        return (self.paint,)

    def gettransform(self) -> Affine2D:
        return (
            Affine2D.identity()
            .translate(self.center[0], self.center[1])
            .scale(self.scaleX, self.scaleY)
            .translate(-self.center[0], -self.center[1])
        )


@dataclasses.dataclass(frozen=True)
class PaintScaleUniform(Paint):
    format: ClassVar[int] = int(ot.PaintFormat.PaintScaleUniform)
    paint: Paint
    scale: float = 1.0

    def colors(self):
        yield from self.paint.colors()

    def to_ufo_paint(self, colors):
        paint = {
            "Format": self.format,
            "Paint": self.paint.to_ufo_paint(colors),
            "scale": self.scale,
        }
        return paint

    def children(self) -> Iterable[Paint]:
        return (self.paint,)

    def gettransform(self) -> Affine2D:
        return Affine2D.identity().scale(self.scale)


@dataclasses.dataclass(frozen=True)
class PaintScaleUniformAroundCenter(Paint):
    format: ClassVar[int] = int(ot.PaintFormat.PaintScaleUniformAroundCenter)
    paint: Paint
    scale: float = 1.0
    center: Point = Point()

    def colors(self):
        yield from self.paint.colors()

    def to_ufo_paint(self, colors):
        paint = {
            "Format": self.format,
            "Paint": self.paint.to_ufo_paint(colors),
            "scale": self.scale,
            "centerX": self.center[0],
            "centerY": self.center[1],
        }
        return paint

    def children(self) -> Iterable[Paint]:
        return (self.paint,)

    def gettransform(self) -> Affine2D:
        return (
            Affine2D.identity()
            .translate(self.center[0], self.center[1])
            .scale(self.scale)
            .translate(-self.center[0], -self.center[1])
        )


@dataclasses.dataclass(frozen=True)
class PaintRotate(Paint):
    format: ClassVar[int] = int(ot.PaintFormat.PaintRotate)
    paint: Paint
    angle: float = 0.0

    def colors(self):
        yield from self.paint.colors()

    def to_ufo_paint(self, colors):
        paint = {
            "Format": self.format,
            "Paint": self.paint.to_ufo_paint(colors),
            "angle": self.angle,
        }
        return paint

    def children(self) -> Iterable[Paint]:
        return (self.paint,)

    def gettransform(self) -> Affine2D:
        return Affine2D.identity().rotate(radians(self.angle))


@dataclasses.dataclass(frozen=True)
class PaintRotateAroundCenter(Paint):
    format: ClassVar[int] = int(ot.PaintFormat.PaintRotateAroundCenter)
    paint: Paint
    angle: float = 0.0
    center: Point = Point()

    def colors(self):
        yield from self.paint.colors()

    def to_ufo_paint(self, colors):
        paint = {
            "Format": self.format,
            "Paint": self.paint.to_ufo_paint(colors),
            "angle": self.angle,
            "centerX": self.center[0],
            "centerY": self.center[1],
        }
        return paint

    def children(self) -> Iterable[Paint]:
        return (self.paint,)

    def gettransform(self) -> Affine2D:
        return Affine2D.identity().rotate(
            radians(self.angle), self.center[0], self.center[1]
        )


@dataclasses.dataclass(frozen=True)
class PaintSkew(Paint):
    format: ClassVar[int] = int(ot.PaintFormat.PaintSkew)
    paint: Paint
    xSkewAngle: float = 0.0
    ySkewAngle: float = 0.0

    def colors(self):
        yield from self.paint.colors()

    def to_ufo_paint(self, colors):
        paint = {
            "Format": self.format,
            "Paint": self.paint.to_ufo_paint(colors),
            "xSkewAngle": self.xSkewAngle,
            "ySkewAngle": self.ySkewAngle,
        }
        return paint

    def children(self) -> Iterable[Paint]:
        return (self.paint,)

    def gettransform(self) -> Affine2D:
        return Affine2D.identity().skew(
            -radians(self.xSkewAngle), radians(self.ySkewAngle)
        )


@dataclasses.dataclass(frozen=True)
class PaintSkewAroundCenter(Paint):
    format: ClassVar[int] = int(ot.PaintFormat.PaintSkewAroundCenter)
    paint: Paint
    xSkewAngle: float = 0.0
    ySkewAngle: float = 0.0
    center: Point = Point()

    def colors(self):
        yield from self.paint.colors()

    def to_ufo_paint(self, colors):
        paint = {
            "Format": self.format,
            "Paint": self.paint.to_ufo_paint(colors),
            "xSkewAngle": self.xSkewAngle,
            "ySkewAngle": self.ySkewAngle,
            "centerX": self.center[0],
            "centerY": self.center[1],
        }
        return paint

    def children(self) -> Iterable[Paint]:
        return (self.paint,)

    def gettransform(self) -> Affine2D:
        return (
            Affine2D.identity()
            .translate(self.center[0], self.center[1])
            .skew(-radians(self.xSkewAngle), radians(self.ySkewAngle))
            .translate(-self.center[0], -self.center[1])
        )


@dataclasses.dataclass(frozen=True)
class PaintComposite(Paint):
    format: ClassVar[int] = int(ot.PaintFormat.PaintComposite)
    mode: CompositeMode
    source: Paint
    backdrop: Paint

    def colors(self):
        yield from self.source.colors()
        yield from self.backdrop.colors()

    def to_ufo_paint(self, colors):
        paint = {
            "Format": self.format,
            "CompositeMode": self.mode.name.lower(),
            "SourcePaint": self.source.to_ufo_paint(colors),
            "BackdropPaint": self.backdrop.to_ufo_paint(colors),
        }
        return paint

    def children(self) -> Iterable[Paint]:
        return (self.source, self.backdrop)


def is_transform(paint_or_format) -> bool:
    if isinstance(paint_or_format, Paint):
        paint_or_format = paint_or_format.format
    return (
        ot.PaintFormat.PaintTransform
        <= paint_or_format
        <= ot.PaintFormat.PaintVarSkewAroundCenter
    )


def is_gradient(paint_or_format) -> bool:
    if isinstance(paint_or_format, Paint):
        paint_or_format = paint_or_format.format
    return (
        ot.PaintFormat.PaintLinearGradient
        <= paint_or_format
        <= ot.PaintFormat.PaintVarSweepGradient
    )


def transformed(transform: Affine2D, target: Paint) -> Paint:
    if transform == Affine2D.identity():
        return target

    sx, b, c, sy, dx, dy = transform

    # Int16 translation?
    if (dx, dy) != (0, 0) and Affine2D.identity().translate(dx, dy) == transform:
        if int16_safe(dx, dy):
            return PaintTranslate(paint=target, dx=dx, dy=dy)

    # Scale?
    # If all we have are scale and translation this is pure scaling
    # If b,c are present this is some sort of rotation or skew
    if (sx, sy) != (1, 1) and (b, c) == (0, 0) and f2dot14_safe(sx, sy):
        if (dx, dy) == (0, 0):
            if almost_equal(sx, sy):
                return PaintScaleUniform(paint=target, scale=sx)
            else:
                return PaintScale(paint=target, scaleX=sx, scaleY=sy)
        else:
            # translated scaling is the same as scale around a non-origin center
            # If you trace through translate, scale, translate you get:
            # dx = (1 - sx) * cx
            # cx = dx / (1 - sx)  # undefined if sx == 1; if so dx should == 0
            # so, as long as (1==sx) == (0 == dx) we're good
            if (1 == sx) == (0 == dx) and (1 == sy) == (0 == dy):
                cx = 0
                if sx != 1:
                    cx = dx / (1 - sx)
                cy = 0
                if sy != 1:
                    cy = dy / (1 - sy)
                if int16_safe(cx, cy):
                    if almost_equal(sx, sy):
                        return PaintScaleUniformAroundCenter(
                            paint=target, scale=sx, center=Point(cx, cy)
                        )
                    else:
                        return PaintScaleAroundCenter(
                            paint=target, scaleX=sx, scaleY=sy, center=Point(cx, cy)
                        )

    # TODO optimize rotations

    # TODO optimize, skew, rotate around center

    return PaintTransform(paint=target, transform=tuple(transform))
