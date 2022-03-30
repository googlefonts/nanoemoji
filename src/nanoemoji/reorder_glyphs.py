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
from typing import Any, Callable, List, NamedTuple, Optional


_COVERAGE_ATTR = "Coverage"  # tables that have one coverage use this name


def _sort_by_gid(
    get_glyph_id: Callable[[str], int],
    glyphs: List[str],
    parallel_list: Optional[List[Any]],
):
    if parallel_list:
        reordered = sorted(
            ((g, e) for g, e in zip(glyphs, parallel_list)),
            key=lambda t: get_glyph_id(t[0]),
        )
        sorted_glyphs, sorted_parallel_list = map(list, zip(*reordered))
        parallel_list[:] = sorted_parallel_list
    else:
        sorted_glyphs = sorted(glyphs, key=get_glyph_id)

    glyphs[:] = sorted_glyphs


def _get_dotted_attr(value: Any, dotted_attr: str) -> Any:
    attr_names = dotted_attr.split(".")
    assert attr_names

    while attr_names:
        attr_name = attr_names.pop(0)
        value = getattr(value, attr_name)
    return value


class ReorderCoverage(NamedTuple):
    # A list that is parallel to Coverage
    parallel_list_attr: Optional[str] = None
    coverage_attr: str = _COVERAGE_ATTR

    def apply(self, font: ttLib.TTFont, value: otBase.BaseTable):
        coverage = _get_dotted_attr(value, self.coverage_attr)

        if type(coverage) is not list:
            # Normal path, process one coverage that might have a parallel list
            parallel_list = None
            if self.parallel_list_attr:
                parallel_list = _get_dotted_attr(value, self.parallel_list_attr)
                assert (
                    type(parallel_list) is list
                ), f"{self.parallel_list_attr} should be a list"
                assert len(parallel_list) == len(coverage.glyphs), "Nothing makes sense"

            _sort_by_gid(font.getGlyphID, coverage.glyphs, parallel_list)

        else:
            # A few tables have a list of coverage. No parallel list can exist.
            assert (
                not self.parallel_list_attr
            ), f"Can't have multiple coverage AND a parallel list; {self}"
            for coverage_entry in coverage:
                _sort_by_gid(font.getGlyphID, coverage_entry.glyphs, None)


# (Type, Optional Format) => List[ReorderCoverage]
# Encodes the relationships Cosimo identified
_COVERAGE_REORDER = {
    # GPOS
    (ot.SinglePos, 1): [ReorderCoverage()],
    (ot.SinglePos, 2): [ReorderCoverage(parallel_list_attr="Value")],
    (ot.PairPos, 1): [ReorderCoverage(parallel_list_attr="PairSet")],
    (ot.PairPos, 2): [ReorderCoverage()],
    (ot.CursivePos, 1): [ReorderCoverage(parallel_list_attr="EntryExitRecord")],
    (ot.MarkBasePos, 1): [
        ReorderCoverage(
            coverage_attr="MarkCoverage", parallel_list_attr="MarkArray.MarkRecord"
        ),
        ReorderCoverage(
            coverage_attr="BaseCoverage", parallel_list_attr="BaseArray.BaseRecord"
        ),
    ],
    (ot.MarkLigPos, 1): [
        ReorderCoverage(
            coverage_attr="MarkCoverage", parallel_list_attr="MarkArray.MarkRecord"
        ),
        ReorderCoverage(
            coverage_attr="LigatureCoverage",
            parallel_list_attr="LigatureArray.LigatureAttach",
        ),
    ],
    (ot.MarkMarkPos, 1): [
        ReorderCoverage(
            coverage_attr="Mark1Coverage", parallel_list_attr="Mark1Array.MarkRecord"
        ),
        ReorderCoverage(
            coverage_attr="Mark2Coverage", parallel_list_attr="Mark2Array.Mark2Record"
        ),
    ],
    (ot.ContextPos, 1): [ReorderCoverage(parallel_list_attr="PosRuleSet")],
    (ot.ContextPos, 2): [ReorderCoverage()],
    (ot.ContextPos, 3): [ReorderCoverage()],
    (ot.ChainContextPos, 1): [ReorderCoverage(parallel_list_attr="ChainPosRuleSet")],
    (ot.ChainContextPos, 2): [ReorderCoverage()],
    (ot.ChainContextPos, 3): [
        ReorderCoverage(coverage_attr="BacktrackCoverage"),
        ReorderCoverage(coverage_attr="InputCoverage"),
        ReorderCoverage(coverage_attr="LookAheadCoverage"),
    ],
    # GSUB
    (ot.ContextSubst, 1): [ReorderCoverage(parallel_list_attr="SubRuleSet")],
    (ot.ContextSubst, 2): [ReorderCoverage()],
    (ot.ContextSubst, 3): [ReorderCoverage()],
    (ot.ChainContextSubst, 1): [ReorderCoverage(parallel_list_attr="ChainSubRuleSet")],
    (ot.ChainContextSubst, 2): [ReorderCoverage()],
    (ot.ChainContextSubst, 3): [
        ReorderCoverage(coverage_attr="BacktrackCoverage"),
        ReorderCoverage(coverage_attr="InputCoverage"),
        ReorderCoverage(coverage_attr="LookAheadCoverage"),
    ],
    (ot.ReverseChainSingleSubst, 1): [
        ReorderCoverage(parallel_list_attr="Substitute"),
        ReorderCoverage(coverage_attr="BacktrackCoverage"),
        ReorderCoverage(coverage_attr="LookAheadCoverage"),
    ],
    # GDEF
    (ot.AttachList, None): [ReorderCoverage(parallel_list_attr="AttachPoint")],
    (ot.LigCaretList, None): [ReorderCoverage(parallel_list_attr="LigGlyph")],
    (ot.MarkGlyphSetsDef, None): [ReorderCoverage()],
    # MATH
    (ot.MathGlyphInfo, None): [ReorderCoverage(coverage_attr="ExtendedShapeCoverage")],
    (ot.MathItalicsCorrectionInfo, None): [
        ReorderCoverage(parallel_list_attr="ItalicsCorrection")
    ],
    (ot.MathTopAccentAttachment, None): [
        ReorderCoverage(
            coverage_attr="TopAccentCoverage", parallel_list_attr="TopAccentAttachment"
        )
    ],
    (ot.MathKernInfo, None): [
        ReorderCoverage(
            coverage_attr="MathKernCoverage", parallel_list_attr="MathKernInfoRecords"
        )
    ],
    (ot.MathVariants, None): [
        ReorderCoverage(
            coverage_attr="VertGlyphCoverage",
            parallel_list_attr="VertGlyphConstruction",
        ),
        ReorderCoverage(
            coverage_attr="HorizGlyphCoverage",
            parallel_list_attr="HorizGlyphConstruction",
        ),
    ],
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

    coverage_containers = {"GDEF", "GPOS", "GSUB", "MATH"}
    for tag in coverage_containers:
        if tag in font.keys():
            for path in bfs_base_table(font[tag].table, f'font["{tag}"]'):
                # print(_access_path(path))
                value = path[-1].value
                reorder_key = (type(value), getattr(value, "Format", None))
                for reorder in _COVERAGE_REORDER.get(reorder_key, []):
                    reorder.apply(font, value)
