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

# Integration tests for nanoemoji.maximum_color

from fontTools import ttLib
import pytest
import sys
from test_helper import cleanup_temp_dirs, locate_test_file, run, run_nanoemoji


@pytest.fixture(scope="module", autouse=True)
def _cleanup_temporary_dirs():
    # The mkdtemp() docs say the user is responsible for deleting the directory
    # and its contents when done with it. So we use an autouse fixture that
    # automatically removes all the temp dirs at the end of the test module
    yield
    # teardown happens after the 'yield'
    cleanup_temp_dirs()


def test_build_colr_from_svg():
    tmp_dir = run_nanoemoji(
        (
            "--color_format",
            "picosvg",
            locate_test_file("emoji_u42.svg"),
        )
    )

    svg_font_file = tmp_dir / "Font.ttf"
    assert svg_font_file.is_file()

    # We must have COLR!
    run(
        (
            sys.executable,
            "-m",
            "nanoemoji.maximum_color",
            "--build_dir",
            tmp_dir / "maximum_color",
            svg_font_file,
        )
    )

    maxmium_font_file = tmp_dir / "maximum_color" / "Font.ttf"
    assert maxmium_font_file.is_file()

    svg_font = ttLib.TTFont(svg_font_file)
    maxmium_font_file = ttLib.TTFont(maxmium_font_file)

    assert set(maxmium_font_file.keys()) == set(svg_font.keys()) | {"COLR", "CPAL"}
