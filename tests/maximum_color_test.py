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


@pytest.mark.parametrize(
    "color_format, expected_new_tables",
    [
        ("picosvg", {"COLR", "CPAL"}),
        ("glyf_colr_1", {"SVG "}),
    ],
)
def test_build_maximum_font(color_format, expected_new_tables):
    tmp_dir = run_nanoemoji(
        (
            "--color_format",
            color_format,
            locate_test_file("emoji_u42.svg"),
        )
    )

    initial_font_file = tmp_dir / "Font.ttf"
    assert initial_font_file.is_file()

    # Moar color
    run(
        (
            sys.executable,
            "-m",
            "nanoemoji.maximum_color",
            "--build_dir",
            tmp_dir / "maximum_color",
            initial_font_file,
        )
    )

    maxmium_font_file = tmp_dir / "maximum_color" / "Font.ttf"
    assert maxmium_font_file.is_file()

    initial_font = ttLib.TTFont(initial_font_file)
    maximum_font = ttLib.TTFont(maxmium_font_file)
    assert set(maximum_font.keys()) == set(initial_font.keys()) | expected_new_tables
