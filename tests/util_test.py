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
from nanoemoji.util import dfs_base_table, SubTablePath
import os
from pathlib import Path
import pytest


def _access_path(path: SubTablePath):
    access_path = ""
    for entry in path:
        if not entry.name:
            continue
        access_path += entry.name
        if entry.index is not None:
            access_path += f"[{entry.index}]"
    return access_path


def test_traverse_ot_data():
    # TEMPORARY
    location = (
        Path.home()
        / "oss/bungee/fonts/Bungee_Color_Fonts/BungeeColor-Regular_colr_Windows.ttf"
    )
    assert location.is_file()

    font = ttLib.TTFont(location)

    for path in dfs_base_table(font["GSUB"].table):
        print(_access_path(path), type(path[-1].value))

    assert False, "TEMPORARY TEST"
