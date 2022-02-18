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
from fontTools.ttLib.tables import otTables as ot
from lxml import etree  # pytype: disable=import-error
from nanoemoji import config
import os
from pathlib import Path
from picosvg.svg import SVG
from picosvg.svg_transform import Affine2D
import pytest
import shutil
import subprocess
import tempfile
from test_helper import assert_expected_ttx, color_font_config, locate_test_file


RESVG_PATH = shutil.which("resvg")


_TEMPORARY_DIRS = set()


def _mkdtemp() -> Path:
    tmp_dir = Path(tempfile.mkdtemp())
    assert tmp_dir not in _TEMPORARY_DIRS
    _TEMPORARY_DIRS.add(tmp_dir)
    return tmp_dir


@pytest.fixture(scope="module", autouse=True)
def _cleanup_temporary_dirs():
    # The mkdtemp() docs say the user is responsible for deleting the directory
    # and its contents when done with it. So we use an autouse fixture that
    # automatically removes all the temp dirs at the end of the test module
    yield
    # teardown happens after the 'yield'
    for tmp_dir in _TEMPORARY_DIRS:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def _svg_element_names(xpath, svg_content):
    return tuple(
        etree.QName(e).localname
        for e in SVG.fromstring(svg_content).xpath(xpath.replace("/", "/svg:"))
    )


def _svg_element_attributes(xpath, svg_content):
    return SVG.fromstring(svg_content).xpath_one(xpath.replace("/", "/svg:")).attrib


def _run(cmd, tmp_dir=None):
    if not tmp_dir:
        tmp_dir = _mkdtemp()

    cmd = (
        "nanoemoji",
        "--build_dir",
        str(tmp_dir),
    ) + tuple(str(c) for c in cmd)
    print("subprocess:", " ".join(cmd))  # very useful on failure
    # We need to find nanoemoji and (optionally) resvg
    bin_paths = [str(Path(shutil.which("nanoemoji")).parent)]
    if RESVG_PATH:
        bin_paths.append(str(Path(RESVG_PATH).parent))
    env = {
        "PATH": os.pathsep.join(bin_paths),
        # We may need to find test modules
        "PYTHONPATH": os.pathsep.join((str(Path(__file__).parent),)),
    }
    # Needed for windows CI to function; ref https://github.com/appveyor/ci/issues/1995
    if "SYSTEMROOT" in os.environ:
        env["SYSTEMROOT"] = os.environ["SYSTEMROOT"]

    subprocess.run(cmd, check=True, env=env)

    assert (tmp_dir / "build.ninja").is_file()

    return tmp_dir


def test_build_static_font_default_config_cli_svg_list():
    tmp_dir = _run((locate_test_file("minimal_static/svg/61.svg"),))

    font = TTFont(tmp_dir / "Font.ttf")
    assert "fvar" not in font


def _build_and_check_ttx(config_overrides, svgs, expected_ttx):
    config_file = _mkdtemp() / "config.toml"
    font_config, _ = color_font_config(
        config_overrides, svgs, tmp_dir=config_file.parent
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
    # transform OT-SVG=>UPEM is not identity
    g_attrs = _svg_element_attributes("/svg/g", svg_content)
    assert "transform" in g_attrs
    transform = Affine2D.fromstring(g_attrs["transform"])
    assert transform != Affine2D.identity(), transform


def test_build_glyf_colr_1_and_picosvg_font():
    tmp_dir = _run(
        (locate_test_file("minimal_static/config_glyf_colr_1_and_picosvg.toml"),)
    )

    font = TTFont(tmp_dir / "Font.ttf")

    assert "COLR" in font
    assert "SVG " in font


@pytest.mark.skipif(RESVG_PATH is None, reason="resvg not installed")
def test_build_sbix_font():
    tmp_dir = _run((locate_test_file("minimal_static/config_sbix.toml"),))

    font = TTFont(tmp_dir / "Font.ttf")

    assert "sbix" in font


@pytest.mark.skipif(RESVG_PATH is None, reason="resvg not installed")
def test_build_cbdt_font():
    tmp_dir = _run((locate_test_file("minimal_static/config_cbdt.toml"),))

    font = TTFont(tmp_dir / "Font.ttf")

    assert "CBDT" in font
    assert "CBLC" in font


@pytest.mark.skipif(RESVG_PATH is None, reason="resvg not installed")
def test_build_glyf_colr_1_and_picosvg_and_cbdt_font():
    tmp_dir = _run(
        (
            locate_test_file(
                "minimal_static/config_glyf_colr_1_and_picosvg_and_cbdt.toml"
            ),
        )
    )

    font = TTFont(tmp_dir / "Font.ttf")

    assert "COLR" in font
    assert "SVG " in font
    assert "CBDT" in font
    assert "CBLC" in font


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
            "--color_format=glyf_colr_1_and_picosvg",
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


# https://github.com/googlefonts/nanoemoji/issues/367
def test_path_to_src_matters():
    def _glyph(font):
        assert font["COLR"].version == 1
        colr_table = font["COLR"].table
        assert colr_table.BaseGlyphList.BaseGlyphCount == 1
        paint = colr_table.BaseGlyphList.BaseGlyphPaintRecord[0].Paint
        assert paint.Format == ot.PaintFormat.PaintGlyph
        return font["glyf"][paint.Glyph]

    tomls = [
        "multi_toml/a.toml",
        "multi_toml/b.toml",
    ]

    tmp_dir = _run(tuple(locate_test_file(toml) for toml in tomls))

    font_a = TTFont(tmp_dir / "A.ttf")
    font_b = TTFont(tmp_dir / "B.ttf")

    # Each font should define a single PaintGlyph and the glyph it uses shouldn't be identical
    assert _glyph(font_a) != _glyph(font_b)


def test_input_symlinks_support(tmp_path):
    # Symbolic links are not resolved but treated as distinct input files.
    shutil.copyfile(locate_test_file("emoji_u42.svg"), tmp_path / "emoji_u42.svg")
    # $ ln -s emoji_u43.svg emoji_u42.svg
    (tmp_path / "emoji_u43.svg").symlink_to(tmp_path / "emoji_u42.svg")
    # $ ln -s emoji_u66_69.svg emoji_u42.svg
    (tmp_path / "emoji_u66_69.svg").symlink_to(tmp_path / "emoji_u42.svg")

    _run(
        (
            tmp_path / "emoji_u42.svg",  # glyph 'B'
            tmp_path / "emoji_u43.svg",  # glyph 'C'
            tmp_path / "emoji_u66_69.svg",  # ligature 'f_i'
            "--keep_glyph_names",
        ),
        tmp_dir=tmp_path,
    )

    font = TTFont(tmp_path / "Font.ttf")
    colr_table = font["COLR"].table

    # check we get three identical color glyphs with the same Paint
    assert colr_table.BaseGlyphList.BaseGlyphCount == 3

    assert colr_table.BaseGlyphList.BaseGlyphPaintRecord[0].BaseGlyph == "B"
    assert colr_table.BaseGlyphList.BaseGlyphPaintRecord[1].BaseGlyph == "C"
    assert colr_table.BaseGlyphList.BaseGlyphPaintRecord[2].BaseGlyph == "f_i"

    assert (
        colr_table.BaseGlyphList.BaseGlyphPaintRecord[0].Paint
        == (colr_table.BaseGlyphList.BaseGlyphPaintRecord[1].Paint)
        == colr_table.BaseGlyphList.BaseGlyphPaintRecord[2].Paint
    )

    # check that the symlinked ligature was built as usual
    ligatures = font["GSUB"].table.LookupList.Lookup[0].SubTable[0].ligatures
    assert "f" in ligatures
    assert len(ligatures["f"]) == 1
    assert ligatures["f"][0].Component == ["i"]
    assert ligatures["f"][0].LigGlyph == "f_i"
