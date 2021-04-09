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
from nanoemoji import config
from pathlib import Path
from picosvg.svg import SVG
import pytest
import subprocess
import tempfile
from test_helper import assert_expected_ttx, color_font_config, locate_test_file


def _svg_element_names(xpath, svg_content):
    return tuple(
        etree.QName(e).localname
        for e in SVG.fromstring(svg_content).xpath(xpath.replace("/", "/svg:"))
    )


def _run(cmd, tmp_dir=None):
    if not tmp_dir:
        tmp_dir = tempfile.mkdtemp()

    cmd = (
        "nanoemoji",
        "--build_dir",
        str(tmp_dir),
    ) + tuple(str(c) for c in cmd)
    print("subprocess:", " ".join(cmd))  # very useful on failure
    subprocess.run(cmd, check=True)

    tmp_dir = Path(tmp_dir)
    assert (tmp_dir / "build.ninja").is_file()

    return tmp_dir


def test_build_static_font_default_config_cli_svg_list():
    tmp_dir = _run((locate_test_file("minimal_static/svg/61.svg"),))

    font = TTFont(tmp_dir / "Font.ttf")
    assert "fvar" not in font


def _build_and_check_ttx(config_overrides, svgs, expected_ttx):
    config_file = Path(tempfile.mkdtemp()) / "config.toml"
    font_config, _ = color_font_config(
        config_overrides, svgs, tmp_dir=str(config_file.parent)
    )
    config.write(config_file, font_config)
    print(config_file, font_config)

    _run(("--config", str(config_file)), tmp_dir=config_file.parent)
    font = TTFont(config_file.parent / "Font.ttf")
    assert_expected_ttx(svgs, font, expected_ttx)


# Drop content outside viewbox
# https://github.com/googlefonts/nanoemoji/issues/200
def test_build_static_font_clipped():
    _build_and_check_ttx({}, ("emoji_u25fd.svg",), "outside_viewbox_clipped_colr_1.ttx")


# Retain content outside viewbox
# https://github.com/googlefonts/nanoemoji/issues/200
def test_build_static_font_unclipped():
    _build_and_check_ttx(
        {"clip_to_viewbox": False},
        ("emoji_u25fd.svg",),
        "outside_viewbox_not_clipped_colr_1.ttx",
    )


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
    svg_content = font["SVG "].docList[0][0]
    # one group introduced
    assert _svg_element_names("/svg/*", svg_content) == ("g",), svg_content
    # rect stayed rect, fill non ellipse still around
    assert _svg_element_names("/svg/g/*", svg_content) == (
        "path",
        "rect",
        "ellipse",
    ), svg_content
