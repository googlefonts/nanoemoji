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

from nanoemoji import config
from pathlib import Path
import pytest
from test_helper import TEST_DATA_DIR, locate_test_file
import shutil
import tempfile
from typing import Iterable


@pytest.mark.parametrize(
    "config_file",
    [
        None,  # the default config file
        "minimal_vf/config.toml",
        "minimal_static/config.toml",
    ],
)
def test_read_write_config(config_file):
    tmp_dir = Path(tempfile.mkdtemp())
    if config_file:
        config_file = locate_test_file(config_file)
        tmp_config = tmp_dir / config_file.name
    else:
        tmp_config = tmp_dir / "the_default.toml"

    original = config.load(config_file)
    config.write(tmp_config, original)
    reloaded = config.load(tmp_config)

    assert original == reloaded

    shutil.rmtree(tmp_dir, ignore_errors=True)


@pytest.mark.parametrize(
    "relative_base, src, expected_files",
    [
        # relative single file
        (
            TEST_DATA_DIR,
            "minimal_static/svg/61.svg",
            {locate_test_file("minimal_static/svg/61.svg")},
        ),
        # relative pattern
        (
            TEST_DATA_DIR,
            "linear_gradient_transform*.svg",
            {
                locate_test_file("linear_gradient_transform.svg"),
                locate_test_file("linear_gradient_transform_2.svg"),
                locate_test_file("linear_gradient_transform_3.svg"),
            },
        ),
        # absolute single file
        (
            TEST_DATA_DIR,
            locate_test_file("minimal_static/svg/61.svg").resolve(),
            {locate_test_file("minimal_static/svg/61.svg")},
        ),
        # absolute pattern
        (
            None,
            TEST_DATA_DIR.resolve() / "**" / "linear_gradient_transform_*.svg",
            {
                locate_test_file("linear_gradient_transform_2.svg"),
                locate_test_file("linear_gradient_transform_3.svg"),
            },
        ),
    ],
)
def test_resolve_src(relative_base, src, expected_files):
    assert set(config._resolve_src(relative_base, str(src))) == expected_files
