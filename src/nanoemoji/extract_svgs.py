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

"""Helpers for extracting svg files from the SVG table."""


import copy
from fontTools import ttLib
from picosvg.svg import SVG
from picosvg.svg_meta import strip_ns
from typing import Iterable, Tuple


def _remove_glyph_elements(svg: SVG, gids_to_remove: Iterable[int]) -> SVG:
    """Strip out unwanted glyph roots.

    We do NOT try to strip unused shared content; that is left for others,
    e.g. picosvg.
    """
    svg = copy.deepcopy(svg)
    for gid in gids_to_remove:
        results = svg.xpath(f"svg:*[@id='glyph{gid}']")
        for result in results:
            parent = result.getparent()
            if parent is not None:
                parent.remove(result)
    return svg


def svg_glyphs(font: ttLib.TTFont) -> Iterable[Tuple[int, SVG]]:
    for raw_svg, min_gid, max_gid in font["SVG "].docList:
        gids = set(range(min_gid, max_gid + 1))
        svg = SVG.fromstring(raw_svg)
        for gid in gids:
            svg_for_gid = svg
            if len(gids) > 1:
                svg_for_gid = _remove_glyph_elements(svg_for_gid, gids - {gid})
            yield (gid, svg_for_gid)
