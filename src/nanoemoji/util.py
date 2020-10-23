# Copyright 2020 Google LLC
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

"""Small helper functions."""

import pathlib
import shlex
from typing import List


def only(filter_fn, iterable):
    it = filter(filter_fn, iterable)
    result = next(it)
    assert next(it, None) is None
    return result


def expand_ninja_response_files(argv: List[str]) -> List[str]:
    """
    Extend argument list with MSVC-style '@'-prefixed response files.

    Ninja build rules support this mechanism to allow passing a very long list of inputs
    that may exceed the shell's maximum command-line length.

    References:
    https://ninja-build.org/manual.html ("Rule variables")
    https://docs.microsoft.com/en-us/cpp/build/reference/at-specify-a-compiler-response-file
    """
    result = []
    for arg in argv:
        if arg.startswith("@"):
            with open(arg[1:], "r") as rspfile:
                rspfile_content = rspfile.read()
            result.extend(shlex.split(rspfile_content))
        else:
            result.append(arg)
    return result
