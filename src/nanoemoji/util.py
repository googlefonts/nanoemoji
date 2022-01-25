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

import os
import contextlib
from functools import partial
from pathlib import Path
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
            result.extend(shlex.split(rspfile_content, posix=os.name == "posix"))
        else:
            result.append(arg)
    return result


def fs_root() -> Path:
    return Path("/").resolve()


def rel(from_path: Path, to_path: Path) -> Path:
    # relative_to(A,B) doesn't like it if B doesn't start with A
    abs_from_path = abspath(from_path)
    abs_to_path = abspath(to_path)
    if abs_from_path.drive != abs_to_path.drive:
        # On Windows, we can't resolve relative paths across drive mount points.
        # We must return the absolute path in this case, or else we get:
        #     ValueError: path is on mount 'D:', start on mount 'C:'
        return abs_to_path
    return Path(os.path.relpath(abs_to_path, abs_from_path))


def abspath(path: Path) -> Path:
    # pathlib.Path.absolute() doesn't do path normalization, whereas Path.resolve()
    # does normalization but also resolves symlinks which sometimes we don't want to
    # so here we use good ol' os.path.abspath.
    return Path(os.path.abspath(path))


@contextlib.contextmanager
def file_printer(filename):
    if filename == "-":  # conventionally means print to stdout
        yield print
    else:
        with open(filename, "w") as f:
            yield partial(print, file=f)
