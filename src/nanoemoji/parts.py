# Copyright 2022 Google LLC
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
"""A cache of reusable parts, esp paths, for whatever purpose you see fit.

Intended to be used as a building block for glyph reuse.

We always apply nop transforms to ensure any command type flips, such as arcs
to cubics, occur. This ensures that if we merge a part file with no transform
with one that has transformation the command types still align.
"""

import dataclasses
from functools import lru_cache, partial, reduce
import json
from nanoemoji.config import FontConfig
from nanoemoji.color_glyph import scale_viewbox_to_font_metrics
from pathlib import Path
from picosvg.geometric_types import Rect
from picosvg.svg import SVG
from picosvg.svg_meta import cmd_coords
from picosvg.svg_reuse import affine_between, normalize
from picosvg.svg_transform import Affine2D
from picosvg.svg_types import SVGPath, SVGShape
from typing import (
    Iterable,
    List,
    MutableMapping,
    NamedTuple,
    NewType,
    Optional,
    Set,
    Tuple,
    Union,
)


PathSource = Union[SVG, "ReusableParts"]


_DEFAULT_ROUND_NDIGITS = 3


@lru_cache(maxsize=1)
def _default_tolerence() -> float:
    return FontConfig().reuse_tolerance


def _is_iterable_of(thing, desired_type) -> bool:
    try:
        it = iter(thing)
    except TypeError:
        return False

    try:
        val = next(it)
        return isinstance(val, desired_type)
    except StopIteration:
        return True


# an SVG style path, e.g. the d attribute of <svg:path/>
Shape = NewType("Shape", str)


# A normalized SVG style path
NormalizedShape = NewType("NormalizedShape", str)


# A set of shapes that normalize to the same path
ShapeSet = NewType("ShapeSet", Set[Shape])


class ReuseResult(NamedTuple):
    transform: Affine2D
    shape: Shape


@lru_cache(maxsize=512)
def _bbox_area(shape: Shape) -> float:
    bbox = SVGPath(d=shape).bounding_box()
    return bbox.w * bbox.h


def _round(shape: SVGShape) -> SVGPath:
    return shape.as_path().round_floats(_DEFAULT_ROUND_NDIGITS)


def as_shape(path: SVGPath) -> Shape:
    # apply a nop transform because some things still change, like arcs to cubics
    path = path.apply_transform(Affine2D.identity())
    return Shape(_round(path).d)


# TODO: create a parts builder and a frozen parts from compute_donors() to more explicitly model the add/use cycle


@dataclasses.dataclass
class ReusableParts:
    version: Tuple[int, int, int] = (1, 0, 0)
    view_box: Rect = Rect(0, 0, 1, 1)
    reuse_tolerance: float = dataclasses.field(default_factory=_default_tolerence)
    shape_sets: MutableMapping[NormalizedShape, ShapeSet] = dataclasses.field(
        default_factory=dict
    )
    _donor_cache: MutableMapping[NormalizedShape, Optional[Shape]] = dataclasses.field(
        default_factory=dict
    )

    def normalize(self, path: str) -> NormalizedShape:
        if self.reuse_tolerance != -1:
            # normalize handles it's own rounding
            # apply a nop transform because some things still change, like arcs to cubics
            norm = NormalizedShape(
                normalize(
                    SVGPath(d=path).apply_transform(Affine2D.identity()),
                    self.reuse_tolerance,
                ).d
            )
        else:
            norm = NormalizedShape(path)
        return norm

    def _add_norm_path(self, norm: NormalizedShape, shape: Shape):
        if norm not in self.shape_sets:
            self.shape_sets[norm] = ShapeSet(set())
        self.shape_sets[norm].add(shape)
        self._donor_cache.pop(norm, None)

    def _add(self, shape: Shape):
        norm = self.normalize(shape)
        self._add_norm_path(norm, shape)

    def add(self, source: PathSource):
        """Combine two sets of parts. Source shapes will be scaled to dest viewbox."""
        if isinstance(source, ReusableParts):
            transform = Affine2D.rect_to_rect(source.view_box, self.view_box)
            shapes = tuple(
                reduce(lambda a, c: a | c, source.shape_sets.values(), set())
            )
        elif isinstance(source, SVG):
            source.checkpicosvg()
            source_box = source.view_box()
            transform = scale_viewbox_to_font_metrics(
                self.view_box, source_box.h, 0, source_box.w
            )
            shapes = tuple(s.as_path() for s in source.shapes())
        else:
            raise ValueError(f"Unknown part source: {type(source)}")

        for shape in shapes:
            if isinstance(shape, str):
                shape = SVGPath(d=shape)
            if transform != Affine2D.identity():
                shape = shape.apply_transform(transform)
            self._add(as_shape(shape))

    def _compute_donor(self, norm: NormalizedShape):
        self._donor_cache[norm] = None  # no solution

        # try to select a donor that can fulfil every member of the set
        # the input shape is in the set so if found we can get from donor => input
        # shrinking a big thing is more likely to result in small #s that fit into
        # more compact PaintTransform variants so try biggest first

        # NOTE there are cases where this picks a suboptimal transform, e.g. a 2x3
        # downscale be used when a scale uniform around center upscale might work
        # Ex SVGPath(d="M8,13 A3 3 0 1 1 2,13 A3 3 0 1 1 8,13 Z")
        #    SVGPath(d="M11,5 A2 2 0 1 1 7,5 A2 2 0 1 1 11,5 Z")
        # A fancier implementation would factor in the # of occurences and the cost
        # based on which shape is selected as donor if there are many possibilities.

        svg_paths = sorted(
            self.shape_sets[norm], key=lambda s: (_bbox_area(s), s), reverse=True
        )
        svg_paths = [SVGPath(d=s) for s in svg_paths]

        for svg_path in svg_paths:
            if all(
                affine_between(svg_path, svg_path2, self.reuse_tolerance) is not None
                for svg_path2 in svg_paths
            ):
                # Do NOT use as_shape; these paths already passed through it
                self._donor_cache[norm] = Shape(svg_path.d)
                break

    def compute_donors(self):
        self._donor_cache.clear()
        for norm in self.shape_sets:
            self._compute_donor(norm)

    def is_reused(self, shape: SVGPath) -> bool:
        shape = as_shape(shape)
        norm = self.normalize(shape)
        if norm not in self.shape_sets:
            return False
        if len(self.shape_sets[norm]) < 2:
            return False
        if norm not in self._donor_cache:
            self._compute_donor(norm)
        return shape == self._donor_cache[norm]  # this shape provides!

    def try_reuse(self, shape: SVGPath) -> Optional[ReuseResult]:
        """Returns the shape and transform to use to build the input shape."""
        shape = as_shape(shape)
        if self.reuse_tolerance == -1:
            return ReuseResult(Affine2D.identity(), shape)

        norm = self.normalize(shape)

        # The whole point is to pre-add, doing it on the fly reduces reuse
        if norm not in self.shape_sets:
            print(self.to_json())
            raise ValueError(
                f"You MUST pre-add your shapes. No set matches normalization {norm} for {shape}."
            )

        if shape not in self.shape_sets[norm]:
            print(self.to_json())
            raise ValueError(f"You MUST pre-add your shapes. {shape} is new to us.")

        if norm not in self._donor_cache:
            assert (
                shape in self.shape_sets[norm]
            ), f"The input shape must be in the group"
            self._compute_donor(norm)

        donor = self._donor_cache[norm]
        if donor is None:
            # bail out, no solution!
            return None

        affine = affine_between(
            SVGPath(d=donor), SVGPath(d=shape), self.reuse_tolerance
        )
        assert (
            affine is not None
        ), f"Should only get here with a solution. Epic fail on {donor}, {shape.d}"
        return ReuseResult(affine, donor)

    def to_json(self):
        json_dict = {
            "version": ".".join(str(v) for v in self.version),
            "reuse_tolerance": self.reuse_tolerance,
            "view_box": " ".join(str(int(v)) for v in self.view_box),
            "shape_sets": [
                {
                    "normalized": n,
                    "shapes": list(s),
                    "donor": self._donor_cache.get(n, ""),
                }
                for n, s in self.shape_sets.items()
            ],
        }
        return json.dumps(json_dict, indent=2)

    @classmethod
    def from_json(cls, string: str) -> "ReusableParts":
        json_dict = json.loads(string)
        parts = ReusableParts()
        parts.version = tuple(int(v) for v in json_dict.pop("version").split("."))
        assert parts.version == (1, 0, 0), f"Bad version {parts.version}"
        parts.view_box = Rect(*(int(v) for v in json_dict.pop("view_box").split(" ")))
        assert parts.view_box[:2] == (
            0,
            0,
        ), f"Must be a viewbox from 0,0 {parts.view_box}"
        parts.reuse_tolerance = float(json_dict.pop("reuse_tolerance"))
        for shape_set_json in json_dict.pop("shape_sets"):
            norm = NormalizedShape(shape_set_json.pop("normalized"))
            shapes = ShapeSet({Shape(s) for s in shape_set_json.pop("shapes")})
            donor = shape_set_json.pop("donor")
            if donor and donor not in shapes:
                raise ValueError("Donor must be in group")
            if shape_set_json:
                raise ValueError(f"Unconsumed input {shape_set_json}")
            parts.shape_sets[norm] = shapes
            if donor != "":
                parts._donor_cache[norm] = donor
        if json_dict:
            raise ValueError(f"Unconsumed input {json_dict}")
        return parts

    @classmethod
    def loadjson(cls, input_file: Path) -> "ReusableParts":
        ext = input_file.suffix.lower()
        if ext != ".json":
            raise ValueError(f"Unknown format {input_file}")
        return cls.from_json(input_file.read_text(encoding="utf-8"))
