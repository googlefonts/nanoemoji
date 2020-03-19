"""Helpers for expressing paint.

Based on https://github.com/googlefonts/colr-gradients-spec/blob/master/colr-gradients-spec.md#structure-of-gradient-colr-v1-extensions.
"""
from colors import Color, css_color
import dataclasses
from enum import Enum
from typing import Tuple


@dataclasses.dataclass(frozen=True)
class Point:
    x: int = 0
    y: int = 0


class Extend(Enum):
  PAD = 0,
  REPEAT = 1,
  REFLECT = 2,

@dataclasses.dataclass(frozen=True)
class ColorStop:
  stopOffset: float = 0.
  color: Color = css_color('black')


@dataclasses.dataclass(frozen=True)
class PaintSolid:
  format: int = 1 
  color: Color = css_color('black')

  def colors(self):
    yield self.color

  def to_ufo_paint(self, colors):
    return {
        "format": self.format,
        "paletteIndex": colors.index(self.color),
        "transparency": self.color.alpha,
    }


@dataclasses.dataclass(frozen=True)
class PaintLinearGradient:
  format: int = 2
  extend: Extend = Extend.PAD
  stops: Tuple[ColorStop,...] = dataclasses.field(default_factory=lambda: ())
  p0: Point = Point()
  p1: Point = Point()
  p2: Point = None

  def colors(self):
    for stop in self.stops:
      yield stop.color

  def to_ufo_paint(self, colors):
    result = {
        "format": self.format,
        "colorLine": {
            "stops": [
                {
                    "offset": stop.stopOffset,
                    "paletteIndex": colors.index(stop.color)
                }
                for stop in self.stops
            ]
        },
        "p0": dataclasses.astuple(self.p0),
        "p1": dataclasses.astuple(self.p1),
    }
    if self.p2:
      result["p2"] = dataclasses.astuple(self.p2)
    return result

@dataclasses.dataclass(frozen=True)
class PaintRadialGradient:
  format: int = 3 
  extend: Extend = Extend.PAD
  stops: Tuple[ColorStop] = dataclasses.field(default_factory=lambda: ())
  c0: Point = Point()
  c1: Point = Point()
  r0: float = 0.
  r1: float = 0.
  # TODO Affine2x2

  def colors(self):
    for stop in self.stops:
      yield stop.color


