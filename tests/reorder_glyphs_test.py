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
from nanoemoji.reorder_glyphs import _COVERAGE_REORDER, _sort_by_gid
from nanoemoji.util import load_fully
import os
from pathlib import Path
import pytest


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
