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


from fontTools import ttLib
from functools import reduce
from nanoemoji.reorder_glyphs import _COVERAGE_REORDER, _sort_by_gid, reorder_glyphs
from nanoemoji.util import load_fully
from nanoemoji import write_font
from nanoemoji.util import only
import os
from pathlib import Path
import pytest
import tempfile
import test_helper


def _dotted_converter(item, dotted_attr):
    attr_names = dotted_attr.split(".")
    assert attr_names

    while attr_names:
        attr_name = attr_names.pop(0)
        item = item.getConverterByName(attr_name)

        # Do we have to descend?
        if attr_names:
            item = item.tableClass()

    return item


def test_metadata_is_valid():
    for (clazz, fmt), reorders in _COVERAGE_REORDER.items():
        instance = clazz()
        instance.Format = fmt
        assert (
            instance.getConverters()
        ), f"Lack of converters suggests {clazz} dislikes Format {fmt}"
        for reorder in reorders:
            assert (
                _dotted_converter(instance, reorder.coverage_attr) is not None
            ), f"No {clazz} {fmt} {reorder.coverage_attr}"
            if reorder.parallel_list_attr:
                assert (
                    _dotted_converter(instance, reorder.parallel_list_attr) is not None
                ), f"No {clazz} {fmt} {reorder.parallel_list_attr}"


def test_sort_just_glyphs():
    glyphs = ["a", "b", "c", "d"]
    gids = [42, 0, 4, 1]

    _sort_by_gid(lambda gn: gids[glyphs.index(gn)], glyphs, None)

    assert glyphs == ["b", "d", "c", "a"]


def test_sort_parallel_list():
    glyphs = ["a", "b", "c", "d"]
    parallel = ["aa", "bb", "cc", "dd"]
    gids = [0, 42, 16, 2]

    _sort_by_gid(lambda gn: gids[glyphs.index(gn)], glyphs, parallel)

    assert glyphs == ["a", "d", "c", "b"]
    assert parallel == ["aa", "dd", "cc", "bb"]


def test_reorder_actual_font():
    def _pair_pos(font):
        # Initial state should be we have a GPOS with PairPos lookup for ab, ac
        pair_pos = only(
            reduce(
                lambda a, c: a + c.SubTable, font["GPOS"].table.LookupList.Lookup, []
            )
        )
        return tuple(
            (
                pair_pos.Coverage.glyphs[i],
                only(pair_set.PairValueRecord).SecondGlyph,
                only(pair_set.PairValueRecord).Value1.XAdvance,
            )
            for i, pair_set in enumerate(pair_pos.PairSet)
        )

    # tell the boxes to get closer together when ordered ab
    # use GPOS, PairPos Format1 which has Coverage and a Value, a parallel sorted List[ValueRecord]
    fea = r"""
    languagesystem DFLT dflt;
    languagesystem latn dflt;

    feature kern {
        position a b -12;
        position b c -16;
    } kern;
    """
    with tempfile.TemporaryDirectory() as temp_dir:
        fea_file = Path(temp_dir) / "fea.fea"
        fea_file.write_text(fea)

        # upem 24, input svgs are on a 0 0 24 24 viewBox
        svgs = tuple(
            test_helper.locate_test_file(f"narrow_rects/{c}.svg") for c in "abc"
        )
        config, glyph_inputs = test_helper.color_font_config(
            {
                "upem": 24,
                "fea_file": fea_file,
            },
            svgs,
            tmp_dir=Path(temp_dir),
            codepoint_fn=lambda svg_file, _: (ord(svg_file.stem),),
        )
        _, font = write_font._generate_color_font(config, glyph_inputs)

        # Initial state
        assert _pair_pos(font) == (("a", "b", -12), ("b", "c", -16))

        # Swap glyph order of a, b
        ai, bi = font.getGlyphID("a"), font.getGlyphID("b")
        new_glyph_order = list(font.getGlyphOrder())
        new_glyph_order[ai], new_glyph_order[bi] = (
            new_glyph_order[bi],
            new_glyph_order[ai],
        )
        reorder_glyphs(font, new_glyph_order)

        # Confirm swap applied to Coverage and pair pos parallel array
        assert _pair_pos(font) == (("b", "c", -16), ("a", "b", -12))
