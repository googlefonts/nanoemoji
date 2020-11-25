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

# Integration tests for nanoemoji

from fontTools.ttLib import TTFont
from lxml import etree  # pytype: disable=import-error
from pathlib import Path
from picosvg.svg import SVG
import pytest
import subprocess
import tempfile
from test_helper import locate_test_file


def _svg_element_names(xpath, svg_content):
    return tuple(
        etree.QName(e).localname
        for e in SVG.fromstring(svg_content).xpath(xpath.replace("/", "/svg:"))
    )


def _run(cmd):
    tmp_dir = tempfile.mkdtemp()

    cmd = (
        "nanoemoji",
        "--build_dir",
        tmp_dir,
    ) + cmd
    print(cmd)  # very useful on failure
    subprocess.run(cmd, check=True)

    tmp_dir = Path(tmp_dir)
    assert (tmp_dir / "build.ninja").is_file()

    return tmp_dir


def test_build_static_font_default_config_cli_svg_list():
    tmp_dir = _run((locate_test_file("minimal_static/svg/61.svg"),))

    font = TTFont(tmp_dir / "Font.ttf")
    assert "fvar" not in font


def test_build_static_font():
    cmd = (
        "--config",
        locate_test_file("minimal_static/config.toml"),
    )
    tmp_dir = _run(cmd)

    font = TTFont(tmp_dir / "Font.ttf")
    assert "fvar" not in font


def test_build_variable_font():
    tmp_dir = _run(
        (
            "--config",
            locate_test_file("minimal_vf/config.toml"),
        )
    )

    font = TTFont(tmp_dir / "MinimalVF.ttf")
    assert "fvar" in font


def test_build_picosvg_font():
    tmp_dir = _run(
        (
            "--config",
            locate_test_file("minimal_static/config_picosvg.toml"),
        )
    )

    font = TTFont(tmp_dir / "Font.ttf")
    # fill=none ellipse dropped, rect became path, everything is under a group
    svg_content = font["SVG "].docList[0][0]
    assert _svg_element_names("/svg/g/*", svg_content) == ("path", "path"), svg_content


def test_build_untouchedsvg_font():
    tmp_dir = _run(
        (
            "--config",
            locate_test_file("minimal_static/config_untouchedsvg.toml"),
        )
    )

    font = TTFont(tmp_dir / "Font.ttf")
    assert "SVG " in font

    font = TTFont(tmp_dir / "Font.ttf")
    # rect stayed rect, fill non ellipse still around, no group introduced
    svg_content = font["SVG "].docList[0][0]
    assert _svg_element_names("/svg/*", svg_content) == (
        "path",
        "rect",
        "ellipse",
    ), svg_content
