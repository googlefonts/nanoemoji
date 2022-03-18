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

"""Helps with glyph reordering.

See https://docs.google.com/document/d/14b8bivUBdWSkeGLIVcqVLBVWNbXXFawguq52D2olvEA/edit for context."""


from fontTools import ttLib
from fontTools.ttLib.tables import otTables as ot
from nanoemoji.util import bfs_base_table, require_fully_loaded, SubTablePath
from typing import List


_COVERAGE_ATTR = "Coverage"  # tables that have one coverage use this name


# (Type, Optional Format) => List of (attr name of Coverage, optional attr name of list sorted by that coverage)
# See Cosimo's doc for context
_REORDER_NEEDED = {
    (ot.SinglePos, 1): [(_COVERAGE_ATTR, None)],
    (ot.SinglePos, 2): [(_COVERAGE_ATTR, "Value")],
    (ot.PairPos, 1): [(_COVERAGE_ATTR, "PairSet")],
    (ot.PairPos, 2): [(_COVERAGE_ATTR, None)],
}


def _access_path(path: SubTablePath):
    path_parts = []
    for entry in path:
        if not entry.name:
            continue
        path_part = entry.name
        if entry.index is not None:
            path_part += f"[{entry.index}]"
        path_parts.append(path_part)
    return ".".join(path_parts)


def reorder_glyphs(font: ttLib.TTFont, new_glyph_order: List[str]):
    # Changing the order of glyphs in a TTFont requires that all tables that use
    # glyph indexes have been fully decompiled (loaded with lazy=False).
    # Cf. https://github.com/fonttools/fonttools/issues/2060

    require_fully_loaded(font)

    font.setGlyphOrder(new_glyph_order)
    # glyf table is special and needs its own glyphOrder...
    font["glyf"].glyphOrder = new_glyph_order

    # TODO also GSUB, GDEF, MATH ... see Cosimo's Doc. For now just GPOS for testing purposes.
    coverage_containers = {"GPOS"}
    for tag in coverage_containers:
        if tag in font.keys():
            for path in bfs_base_table(font[tag].table):
                print(_access_path(path))
                value = path[-1].value
                reorder_key = (type(value), getattr(value, "Format", None))
                if reorder_key in _REORDER_NEEDED:
                    print("OMG need to reorder", reorder_key)