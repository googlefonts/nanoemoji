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

from nanoemoji import codepoints
import pytest


@pytest.mark.parametrize(
    "filename, expected_codepoints",
    [
        # Noto Emoji, single codepoint
        ("emoji_u1f378.svg", (0x1F378,)),
        # Noto Emoji, multiple codepoints
        ("emoji_u1f385_1f3fb.svg", (0x1F385, 0x1F3FB)),
        # Noto Emoji, lots of codepoints!
        (
            "emoji_u1f469_1f3fd_200d_1f91d_200d_1f468_1f3ff.svg",
            (0x1F469, 0x1F3FD, 0x200D, 0x1F91D, 0x200D, 0x1F468, 0x1F3FF),
        ),
        # Twemoji, single codepoint
        ("2198.svg", (0x2198,)),
        # Twemoji, multiple codepoints
        (
            "1f9d1-200d-1f91d-200d-1f9d1.svg",
            (0x1F9D1, 0x200D, 0x1F91D, 0x200D, 0x1F9D1),
        ),
    ],
)
def test_codepoints_from_filename(filename, expected_codepoints):
    assert expected_codepoints == codepoints.from_filename(filename)
