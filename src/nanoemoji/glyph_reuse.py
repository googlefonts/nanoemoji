# Copyright 2021 Google LLC
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
#
# Helper for detecting glyph reuse


from absl import logging
import dataclasses
from nanoemoji import parts
from nanoemoji.parts import ReuseResult, ReusableParts
from picosvg.geometric_types import Rect
from picosvg.svg_transform import Affine2D
from picosvg.svg_types import SVGPath
from typing import (
    MutableMapping,
    NamedTuple,
    Optional,
    Set,
)
from .fixed import fixed_safe


@dataclasses.dataclass
class GlyphReuseCache:
    _reusable_parts: ReusableParts
    _shape_to_glyph: MutableMapping[parts.Shape, str] = dataclasses.field(
        default_factory=dict
    )
    _glyph_to_shape: MutableMapping[str, parts.Shape] = dataclasses.field(
        default_factory=dict
    )

    def try_reuse(self, path: str, path_view_box: Rect) -> ReuseResult:
        assert path[0].upper() == "M", path

        path = SVGPath(d=path)
        if path_view_box != self._reusable_parts.view_box:
            print(path, path_view_box, self._reusable_parts.view_box)
            path = path.apply_transform(
                Affine2D.rect_to_rect(path_view_box, self._reusable_parts.view_box)
            )

        maybe_reuse = self._reusable_parts.try_reuse(path)

        # https://github.com/googlefonts/nanoemoji/issues/313 avoid out of bounds affines
        if maybe_reuse is not None and not fixed_safe(*maybe_reuse.transform):
            logging.warning(
                "affine_between overflows Fixed: %s %s, %s",
                path,
                maybe_reuse.shape,
                maybe_reuse.transform,
            )
            maybe_reuse = None
        if maybe_reuse is None:
            maybe_reuse = ReuseResult(Affine2D.identity(), parts.as_shape(path))
        return maybe_reuse

    def set_glyph_for_path(self, glyph_name: str, path: str):
        norm = self._reusable_parts.normalize(path)
        assert norm in self._reusable_parts.shape_sets, f"No shape set for {path}"
        shape = parts.as_shape(SVGPath(d=path))
        assert (
            shape in self._reusable_parts.shape_sets[norm]
        ), f"Not present in shape set: {path}"

        if self._shape_to_glyph.get(shape, glyph_name) != glyph_name:
            raise ValueError(f"{shape} cannot be associated with glyphs")
        if self._glyph_to_shape.get(glyph_name, shape) != shape:
            raise ValueError(f"{glyph_name} cannot be associated with multiple shapes")

        self._shape_to_glyph[shape] = glyph_name
        self._glyph_to_shape[glyph_name] = shape

    def get_glyph_for_path(self, path: str) -> str:
        return self._shape_to_glyph[parts.as_shape(SVGPath(d=path))]

    def forget_glyph_path_associations(self):
        self._shape_to_glyph.clear()
        self._glyph_to_shape.clear()

    def consuming_glyphs(self, path: str) -> Set[str]:
        norm = self._reusable_parts.normalize(path)
        assert (
            norm in self._reusable_parts.shape_sets
        ), f"{path} not associated with any parts!"
        return {
            self._shape_to_glyph[shape]
            for shape in self._reusable_parts.shape_sets[norm]
        }

    def is_known_glyph(self, glyph_name: str):
        return glyph_name in self._glyph_to_shape

    def is_known_path(self, path: str):
        return parts.as_shape(SVGPath(d=path)) in self._shape_to_glyph

    def view_box(self) -> Rect:
        """
        The box within which the shapes in this cache exist.
        """
        return self._reusable_parts.view_box
