# Copyright 2021 Google LLC
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

from nanoemoji.glyphmap import load_from, GlyphMapping
from pathlib import Path
import pytest
import io


@pytest.mark.parametrize(
    "glyph_mapping",
    (
        GlyphMapping(Path("duck/file.svg"), None, (), "q"),
        GlyphMapping(Path("file.svg"), None, (0x32,), "q2"),
        GlyphMapping(Path("duck/file.svg"), None, (0x123, 0x234), "g_123_234"),
        # this name contains a comma, we check that csv.writer correctly escapes it
        GlyphMapping(Path("foo/bar,baz.svg"), None, (0x0041,), "g_41"),
    ),
)
def test_glyphmap_round_trip(glyph_mapping):
    csv_line = glyph_mapping.csv_line()
    out = io.StringIO()

    # Write twice to sanity check we can load a multi-line file
    out.write(csv_line + "\n")
    out.write(csv_line + "\n")

    restored = load_from(io.StringIO(out.getvalue()))
    assert len(restored) == 2
    assert restored[0] == glyph_mapping
    assert restored[1] == glyph_mapping
