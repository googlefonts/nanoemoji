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
from fontTools.ttLib.tables import otBase
from fontTools.ttLib.tables import otTables as ot
from nanoemoji.util import bfs_base_table, require_fully_loaded, SubTablePath
from typing import List, NamedTuple, Optional


_COVERAGE_ATTR = "Coverage"  # tables that have one coverage use this name


class ReorderCoverage(NamedTuple):
    # A list that is parallel to Coverage
    parallel_list_attr: Optional[str] = None
    coverage_attr: str = _COVERAGE_ATTR

    def apply(self, font: ttLib.TTFont, value: otBase.BaseTable):
        print(
            "OMG need to reorder", type(value), self
        )  # TEMPORARY, but leave for Cosimo to find in review. It's a tradition.
        coverage = getattr(value, self.coverage_attr)
        parallel_list = range(len(coverage.glyphs))
        if self.parallel_list_attr:
            parallel_list = getattr(value, self.parallel_list_attr)
            assert type(parallel_list) is list, f"{self.coverage_attr} should be a list"
        assert len(parallel_list) == len(coverage.glyphs), "Nothing makes sense"

        # sort
        reordered = sorted(
            ((g, e) for g, e in zip(coverage.glyphs, parallel_list)),
            key=lambda t: font.getGlyphID(t[0]),
        )

        # update properties
        sorted_glyphs, sorted_parallel_list = map(list, zip(*reordered))
        coverage.glyphs = sorted_glyphs
        if self.parallel_list_attr:
            setattr(value, self.parallel_list_attr, sorted_parallel_list)


# (Type, Optional Format) => List[ReorderCoverage]
# See Cosimo's doc for context
_COVERAGE_REORDER = {
    (ot.SinglePos, 1): [ReorderCoverage()],
    (ot.SinglePos, 2): [ReorderCoverage(parallel_list_attr="Value")],
    (ot.PairPos, 1): [ReorderCoverage(parallel_list_attr="PairSet")],
    (ot.PairPos, 2): [ReorderCoverage()],
    # TODO additional entries
}


def _access_path(path: SubTablePath):
    path_parts = []
    for entry in path:
        path_part = entry.name
        if entry.index is not None:
            path_part += f"[{entry.index}]"
        path_parts.append(path_part)
    return ".".join(path_parts)


def reorder_glyphs(font: ttLib.TTFont, new_glyph_order: List[str]):
    # Changing the order of glyphs in a TTFont requires that all tables that use
    # glyph indexes have been fully.
    # Cf. https://github.com/fonttools/fonttools/issues/2060
    require_fully_loaded(font)

    font.setGlyphOrder(new_glyph_order)

    # TODO also GSUB, GDEF, MATH ... see Cosimo's Doc. For now just GPOS for testing purposes.
    coverage_containers = {"GPOS"}
    for tag in coverage_containers:
        if tag in font.keys():
            for path in bfs_base_table(font[tag].table, f'font["{tag}"]'):
                # print(_access_path(path))
                value = path[-1].value
                reorder_key = (type(value), getattr(value, "Format", None))
                for reorder in _COVERAGE_REORDER.get(reorder_key, []):
                    reorder.apply(font, value)
