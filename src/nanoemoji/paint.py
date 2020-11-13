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

Based on https://github.com/googlefonts/colr-gradients-spec/blob/master/colr-gradients-spec.md#structure-of-gradient-colr-v1-extensions.
"""
import dataclasses
from enum import Enum, IntEnum
from fontTools.ttLib.tables import otTables as ot
from nanoemoji.colors import Color, css_color
from picosvg.geometric_types import Point
from typing import Any, ClassVar, Generator, Mapping, Optional, Sequence, Tuple


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
    SCREEN = 12
    OVERLAY = 13
    DARKEN = 14
    LIGHTEN = 15
    COLOR_DODGE = 16
    COLOR_BURN = 17
    HARD_LIGHT = 18
    SOFT_LIGHT = 19
    DIFFERENCE = 20
    EXCLUSION = 21
    MULTIPLY = 22
    HSL_HUE = 23
    HSL_SATURATION = 24
    HSL_COLOR = 25
    HSL_LUMINOSITY = 26


@dataclasses.dataclass(frozen=True)
class ColorStop:
    stopOffset: float = 0.0
    color: Color = css_color("black")


@dataclasses.dataclass(frozen=True)
class Paint:
    def colors(self) -> Generator[Color, None, None]:
        raise NotImplementedError()

    def to_ufo_paint(self, colors: Sequence[Color]):
        raise NotImplementedError()


@dataclasses.dataclass(frozen=True)
class PaintColrLayers(Paint):
    format: ClassVar[int] = int(ot.Paint.Format.PaintColrLayers)


@dataclasses.dataclass(frozen=True)
class PaintSolid(Paint):
    format: ClassVar[int] = int(ot.Paint.Format.PaintSolid)
    color: Color = css_color("black")

    def colors(self):
        yield self.color

    def to_ufo_paint(self, colors):
        return {
            "format": self.format,
            "paletteIndex": colors.index(self.color.opaque()),
            "alpha": self.color.alpha,
        }


def _ufoColorLine(gradient, colors):
    return {
        "stops": [
            {
                "offset": stop.stopOffset,
                "paletteIndex": colors.index(stop.color.opaque()),
                "alpha": stop.color.alpha,
            }
            for stop in gradient.stops
        ],
        "extend": gradient.extend.name.lower(),
    }


@dataclasses.dataclass(frozen=True)
class PaintLinearGradient(Paint):
    format: ClassVar[int] = int(ot.Paint.Format.PaintLinearGradient)
    extend: Extend = Extend.PAD
    stops: Tuple[ColorStop, ...] = tuple()
    p0: Point = Point()
    p1: Point = Point()
    p2: Point = None  # if undefined, default to p1

    def __post_init__(self):
        # use object.__setattr__ as the dataclass is frozen
        if self.p2 is None:
            object.__setattr__(self, "p2", self.p1)

    def colors(self):
        for stop in self.stops:
            yield stop.color

    def to_ufo_paint(self, colors):
        return {
            "format": self.format,
            "colorLine": _ufoColorLine(self, colors),
            "p0": self.p0,
            "p1": self.p1,
            "p2": self.p2,
        }


@dataclasses.dataclass(frozen=True)
class PaintRadialGradient(Paint):
    format: ClassVar[int] = int(ot.Paint.Format.PaintRadialGradient)
    extend: Extend = Extend.PAD
    stops: Tuple[ColorStop] = tuple()
    c0: Point = Point()
    c1: Point = Point()
    r0: float = 0.0
    r1: float = 0.0

    def colors(self):
        for stop in self.stops:
            yield stop.color

    def to_ufo_paint(self, colors):
        paint = {
            "format": self.format,
            "colorLine": _ufoColorLine(self, colors),
            "c0": self.c0,
            "c1": self.c1,
            "r0": self.r0,
            "r1": self.r1,
        }
        return paint


@dataclasses.dataclass(frozen=True)
class PaintGlyph(Paint):
    format: ClassVar[int] = int(ot.Paint.Format.PaintGlyph)
    glyph: str
    paint: Paint

    def colors(self):
        yield from self.paint.colors()

    def to_ufo_paint(self, colors):
        paint = {
            "format": self.format,
            "glyph": self.glyph,
            "paint": self.paint.to_ufo_paint(colors),
        }
        return paint


@dataclasses.dataclass(frozen=True)
class PaintColrGlyph(Paint):
    format: ClassVar[int] = int(ot.Paint.Format.PaintColrGlyph)
    glyph: str

    def to_ufo_paint(self, _):
        paint = {"format": self.format, "glyph": self.glyph}
        return paint


@dataclasses.dataclass(frozen=True)
class PaintTransform(Paint):
    format: ClassVar[int] = int(ot.Paint.Format.PaintTransform)
    transform: Tuple[float, float, float, float, float, float]
    paint: Paint

    def colors(self):
        yield from self.paint.colors()

    def to_ufo_paint(self, colors):
        paint = {
            "format": self.format,
            "transform": self.transform,
            "paint": self.paint.to_ufo_paint(colors),
        }
        return paint


@dataclasses.dataclass(frozen=True)
class PaintComposite(Paint):
    format: ClassVar[int] = int(ot.Paint.Format.PaintComposite)
    mode: CompositeMode
    source: Paint
    backdrop: Paint

    def colors(self):
        yield from self.source.colors()
        yield from self.backdrop.colors()

    def to_ufo_paint(self, colors):
        paint = {
            "format": self.format,
            "mode": self.mode.name.lower(),
            "source": self.source.to_ufo_paint(colors),
            "backdrop": self.backdrop.to_ufo_paint(colors),
        }
        return paint
