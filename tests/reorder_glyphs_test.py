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
from nanoemoji.reorder_glyphs import reorder_glyphs
from nanoemoji.util import load_fully
import os
from pathlib import Path
import pytest


def test_flip_glyph_order():
    # TEMPORARY
    location = (
        Path.home()
        / "oss/bungee/fonts/Bungee_Color_Fonts/BungeeColor-Regular_colr_Windows.ttf"
    )
    assert location.is_file()

    font = load_fully(ttLib.TTFont(location))

    # reverse the glyph order
    reorder_glyphs(font, reversed(font.getGlyphOrder()))

    assert False, "TEMPORARY TEST"
