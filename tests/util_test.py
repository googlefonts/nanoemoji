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

import sys

from nanoemoji.util import shell_quote, shell_split

import pytest


# Source:
# https://github.com/python/cpython/blob/653e563/Lib/test/test_subprocess.py#L1198-L1214
LIST2CMDLINE_TEST_DATA = [
    (["a b c", "d", "e"], '"a b c" d e'),
    (['ab"c', "\\", "d"], 'ab\\"c \\ d'),
    (['ab"c', " \\", "d"], 'ab\\"c " \\\\" d'),
    (["a\\\\\\b", "de fg", "h"], 'a\\\\\\b "de fg" h'),
    (['a\\"b', "c", "d"], 'a\\\\\\"b c d'),
    (["a\\\\b c", "d", "e"], '"a\\\\b c" d e'),
    (["a\\\\b\\ c", "d", "e"], '"a\\\\b\\ c" d e'),
    (["ab", ""], 'ab ""'),
]
CMDLINE2LIST_TEST_DATA = [(cmdline, args) for args, cmdline in LIST2CMDLINE_TEST_DATA]


@pytest.mark.skipif(not sys.platform.startswith("win"), reason="Windows only")
@pytest.mark.parametrize(
    "args, expected_cmdline",
    LIST2CMDLINE_TEST_DATA,
    ids=[s for _, s in LIST2CMDLINE_TEST_DATA],
)
def test_windows_shell_quote(args, expected_cmdline):
    assert " ".join(shell_quote(s) for s in args) == expected_cmdline


@pytest.mark.skipif(not sys.platform.startswith("win"), reason="Windows only")
@pytest.mark.parametrize(
    "cmdline, expected_args",
    CMDLINE2LIST_TEST_DATA,
    ids=[s for s, _ in CMDLINE2LIST_TEST_DATA],
)
def test_windows_shell_split(cmdline, expected_args):
    assert shell_split(cmdline) == expected_args
