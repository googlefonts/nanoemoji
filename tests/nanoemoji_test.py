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
import os
from pathlib import Path
from picosvg.svg import SVG
import pytest
import shutil
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
    env = {
        # We need to find nanoemoji
        "PATH": os.pathsep.join((str(Path(shutil.which("nanoemoji")).parent),)),
        # We may need to find test modules
        "PYTHONPATH": os.pathsep.join((str(Path(__file__).parent),)),
    }
    # Needed for windows CI to function; ref https://github.com/appveyor/ci/issues/1995
    if "SYSTEMROOT" in os.environ:
        env["SYSTEMROOT"] = os.environ["SYSTEMROOT"]

    subprocess.run(cmd, check=True, env=env)

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

    _run((str(config_file),), tmp_dir=config_file.parent)
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
    tmp_dir = _run((locate_test_file("minimal_vf/config.toml"),))

    font = TTFont(tmp_dir / "MinimalVF.ttf")
    assert "fvar" in font


def test_build_picosvg_font():
    tmp_dir = _run((locate_test_file("minimal_static/config_picosvg.toml"),))

    font = TTFont(tmp_dir / "Font.ttf")
    # fill=none ellipse dropped, rect became path, everything is under a group
    svg_content = font["SVG "].docList[0][0]
    assert _svg_element_names("/svg/g/*", svg_content) == ("path", "path"), svg_content


def test_build_untouchedsvg_font():
    tmp_dir = _run((locate_test_file("minimal_static/config_untouchedsvg.toml"),))

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


def test_the_curious_case_of_the_parentless_reused_el():
    # https://github.com/googlefonts/nanoemoji/issues/346
    svgs = [
        f"parentless_reused_el/emoji_u{codepoints}.svg"
        for codepoints in ("0023_20e3", "1f170", "1f171")
    ]

    tmp_dir = _run(
        (
            "--color_format=picosvg",
            "--pretty_print",
            "--keep_glyph_names",
            *(locate_test_file(svg) for svg in svgs),
        )
    )

    font = TTFont(tmp_dir / "Font.ttf")

    assert_expected_ttx(
        svgs, font, "parentless_reused_el.ttx", include_tables=["GlyphOrder", "SVG "]
    )


def test_glyphmap_games():
    # https://github.com/googlefonts/nanoemoji/issues/354
    # We want to see both glyphs but only one cmap'd, and the use of our special naming scheme
    svgs = [
        "emoji_u25fd.svg",
        "emoji_u42.svg",
    ]

    tmp_dir = _run(
        (
            "--color_format=glyf_colr_1",
            "--keep_glyph_names",
            "--glyphmap_generator=write_test_glyphmap",
            *(locate_test_file(svg) for svg in svgs),
        )
    )

    font = TTFont(tmp_dir / "Font.ttf")

    # We don't really need glyf but ... perhaps it's informative
    assert_expected_ttx(
        svgs, font, "glyphmap_games.ttx", include_tables=["GlyphOrder", "cmap"]
    )


def test_omit_empty_color_glyphs():
    svgs = [
        "emoji_u200c.svg",  # whitespace glyph, contains no paths
        "emoji_u42.svg",
    ]

    tmp_dir = _run(
        (
            "--color_format=glyf_colr_1_and_picosvgz",
            "--pretty_print",
            "--keep_glyph_names",
            *(locate_test_file(svg) for svg in svgs),
        )
    )

    font = TTFont(tmp_dir / "Font.ttf")

    colr = font["COLR"].table
    assert len(colr.BaseGlyphList.BaseGlyphPaintRecord) == 1

    svg = font["SVG "]
    assert len(svg.docList) == 1

    assert_expected_ttx(
        svgs,
        font,
        "omit_empty_color_glyphs.ttx",
        include_tables=["GlyphOrder", "cmap", "glyf", "COLR", "SVG "],
    )
