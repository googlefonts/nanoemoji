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
from test_helper import locate_test_file
import tempfile


@pytest.mark.parametrize(
    "config_file",
    [
        None,  # the default config file
        "minimal_vf/config.toml",
        "minimal_static/config.toml",
    ],
)
@pytest.mark.usefixtures("absl_flags")
def test_read_write_config(config_file):
    tmp_file = Path(tempfile.mkdtemp())
    if config_file:
        config_file = Path(locate_test_file(config_file))
        tmp_file = tmp_file / config_file.name
    else:
        tmp_file = tmp_file / "the_default.toml"

    original = config.load(config_file)
    config.write(tmp_file, original)
    reloaded = config.load(tmp_file)

    assert original == reloaded
