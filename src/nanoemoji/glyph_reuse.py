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
from picosvg.svg_reuse import normalize, affine_between
from picosvg.svg_transform import Affine2D
from picosvg.svg_types import SVGPath
from typing import (
    NamedTuple,
    Optional,
)
from .fixed import fixed_safe


class ReuseResult(NamedTuple):
    glyph_name: str
    transform: Affine2D


class GlyphReuseCache:
    def __init__(self, reuse_tolerance: float):
        self._reuse_tolerance = reuse_tolerance
        self._known_glyphs = set()
        self._reusable_paths = {}

        # normalize tries to remap first two significant vectors to [1 0], [0 1]
        # reuse tolerence is relative to viewbox, which is typically much larger
        # than the space normalize operates in. TODO: better default.
        self._normalize_tolerance = self._reuse_tolerance / 10

    def try_reuse(self, path: str) -> Optional[ReuseResult]:
        """Try to reproduce path as the transformation of another glyph.

        Path is expected to be in font units.

        Returns (glyph name, transform) if possible, None if not.
        """
        assert (
            not path in self._known_glyphs
        ), f"{path} isn't a path, it's a glyph name we've seen before"
        assert path.startswith("M"), f"{path} doesn't look like a path"

        if self._reuse_tolerance == -1:
            return None

        norm_path = normalize(SVGPath(d=path), self._normalize_tolerance).d
        if norm_path not in self._reusable_paths:
            return None

        glyph_name, glyph_path = self._reusable_paths[norm_path]
        affine = affine_between(
            SVGPath(d=glyph_path), SVGPath(d=path), self._reuse_tolerance
        )
        if affine is None:
            logging.warning("affine_between failed: %s %s ", glyph_path, path)
            return None

        # https://github.com/googlefonts/nanoemoji/issues/313 avoid out of bounds affines
        if not fixed_safe(*affine):
            logging.warning(
                "affine_between overflows Fixed: %s %s, %s", glyph_path, path, affine
            )
            return None

        return ReuseResult(glyph_name, affine)

    def add_glyph(self, glyph_name, glyph_path):
        assert glyph_path.startswith("M"), f"{glyph_path} doesn't look like a path"
        if self._reuse_tolerance != -1:
            norm_path = normalize(SVGPath(d=glyph_path), self._normalize_tolerance).d
        else:
            norm_path = glyph_path
        self._reusable_paths[norm_path] = (glyph_name, glyph_path)
        self._known_glyphs.add(glyph_name)

    def is_known_glyph(self, glyph_name):
        return glyph_name in self._known_glyphs
