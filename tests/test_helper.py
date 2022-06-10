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

import difflib
import io
import os
import re
import shutil
import subprocess
import sys
from lxml import etree
from fontTools import ttLib
from nanoemoji import codepoints
from nanoemoji import config
from nanoemoji import features
from nanoemoji.glyph import glyph_name
from nanoemoji import write_font
from nanoemoji.png import PNG
from pathlib import Path
from picosvg.svg import SVG
import pytest
import shutil
import tempfile


def test_data_dir() -> Path:
    return Path(__file__).parent


def locate_test_file(filename) -> Path:
    return test_data_dir() / filename


def parse_svg(filename, locate=False, topicosvg=True):
    if locate:
        filename = locate_test_file(filename)
    svg = SVG.parse(filename)
    return svg.topicosvg(inplace=True) if topicosvg else svg


def rasterize_svg(input_file: Path, output_file: Path, resolution: int = 128) -> PNG:
    resvg = shutil.which("resvg")
    if not resvg:
        pytest.skip("resvg not installed")
    result = subprocess.run(
        [
            resvg,
            "-h",
            f"{resolution}",
            "-w",
            f"{resolution}",
            input_file,
            output_file,
        ]
    )
    return PNG.read_from(output_file)


def color_font_config(
    config_overrides,
    svgs,
    tmp_dir=None,
    codepoint_fn=lambda svg_file, idx: (0xE000 + idx,),
):
    if tmp_dir is None:
        tmp_dir = Path(tempfile.gettempdir())
    svgs = tuple(locate_test_file(s) for s in svgs)
    fea_file = tmp_dir / "test.fea"
    rgi_seqs = tuple(codepoints.from_filename(str(f)) for f in svgs)
    with open(fea_file, "w") as f:
        f.write(features.generate_fea(rgi_seqs))

    font_config = (
        config.load(config_file=None, additional_srcs=svgs)
        ._replace(
            family="UnitTest",
            upem=100,
            ascender=100,
            descender=0,
            width=100,
            keep_glyph_names=True,
            fea_file=str(fea_file),
        )
        ._replace(**config_overrides)
    )

    has_svgs = font_config.has_svgs
    has_picosvgs = font_config.has_picosvgs
    has_bitmaps = font_config.has_bitmaps

    svg_inputs = [(None, None)] * len(svgs)
    if has_svgs:
        svg_inputs = [
            (Path(os.path.relpath(svg)), parse_svg(svg, topicosvg=has_picosvgs))
            for svg in svgs
        ]

    bitmap_inputs = [(None, None)] * len(svgs)
    if has_bitmaps:
        bitmap_inputs = [
            (
                tmp_dir / (svg.stem + ".png"),
                rasterize_svg(
                    svg, tmp_dir / (svg.stem + ".png"), font_config.bitmap_resolution
                ),
            )
            for svg in svgs
        ]

    return (
        font_config,
        [
            write_font.InputGlyph(
                svg_file,
                bitmap_file,
                codepoint_fn(svg_file, idx),
                glyph_name(codepoint_fn(svg_file, idx)),
                svg,
                bitmap,
            )
            for idx, ((svg_file, svg), (bitmap_file, bitmap)) in enumerate(
                zip(svg_inputs, bitmap_inputs)
            )
        ],
    )


def reload_font(ttfont):
    tmp = io.BytesIO()
    ttfont.save(tmp)
    return ttLib.TTFont(tmp)


def _save_actual_ttx(expected_ttx, ttx_content):
    tmp_file = os.path.join(tempfile.gettempdir(), expected_ttx)
    with open(tmp_file, "w") as f:
        f.write(ttx_content)
    return tmp_file


def _strip_inline_bitmaps(ttx_content):
    parser = etree.XMLParser(strip_cdata=False)
    root = etree.fromstring(bytes(ttx_content, encoding="utf-8"), parser=parser)
    made_changes = False

    # bitmapGlyphDataFormat="extfile" doesn't work for sbix so wipe those manually
    for hexdata in root.xpath("//sbix/strike/glyph/hexdata"):
        glyph = hexdata.getparent()
        glyph.remove(hexdata)
        glyph.text = (glyph.attrib["name"] + "." + glyph.attrib["graphicType"]).strip()
        made_changes = True

    # Windows gives \ instead of /, if we see that flip it
    for imagedata in root.xpath("//extfileimagedata"):
        imagedata.attrib["value"] = Path(imagedata.attrib["value"]).name
        made_changes = True

    if not made_changes:
        return ttx_content

    actual_ttx = io.BytesIO()
    etree.ElementTree(root).write(actual_ttx, encoding="utf-8")
    # Glue on the *exact* xml decl and wrapping newline saveXML produces
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        + actual_ttx.getvalue().decode("utf-8")
        + "\n"
    )


def assert_expected_ttx(
    svgs,
    ttfont,
    expected_ttx,
    include_tables=None,
    skip_tables=("head", "hhea", "maxp", "name", "post", "OS/2"),
):
    actual_ttx = io.StringIO()
    # Timestamps inside files #@$@#%@#
    # force consistent Unix newlines (the expected test files use \n too)
    ttfont.saveXML(
        actual_ttx,
        newlinestr="\n",
        tables=include_tables,
        skipTables=skip_tables,
        bitmapGlyphDataFormat="extfile",
    )

    # Elide ttFont attributes because ttLibVersion may change
    actual = re.sub(r'\s+ttLibVersion="[^"]+"', "", actual_ttx.getvalue())

    actual = _strip_inline_bitmaps(actual)

    expected_location = locate_test_file(expected_ttx)
    if os.path.isfile(expected_location):
        with open(expected_location) as f:
            expected = f.read()
    else:
        tmp_file = _save_actual_ttx(expected_ttx, actual)
        raise FileNotFoundError(
            f"Missing expected in {expected_location}. Actual in {tmp_file}"
        )

    if actual != expected:
        for line in difflib.unified_diff(
            expected.splitlines(keepends=True),
            actual.splitlines(keepends=True),
            fromfile=f"{expected_ttx} (expected)",
            tofile=f"{expected_ttx} (actual)",
        ):
            sys.stderr.write(line)
        print(f"SVGS: {svgs}")
        tmp_file = _save_actual_ttx(expected_ttx, actual)
        pytest.fail(f"{tmp_file} != {expected_ttx}")


# Copied from picosvg
def drop_whitespace(svg):
    svg._update_etree()
    for el in svg.svg_root.iter("*"):
        if el.text is not None:
            el.text = el.text.strip()
        if el.tail is not None:
            el.tail = el.tail.strip()


# Copied from picosvg
def pretty_print(svg_tree):
    def _reduce_text(text):
        text = text.strip() if text else None
        return text if text else None

    # lxml really likes to retain whitespace
    for e in svg_tree.iter("*"):
        e.text = _reduce_text(e.text)
        e.tail = _reduce_text(e.tail)

    return etree.tostring(svg_tree, pretty_print=True).decode("utf-8")


# Copied from picosvg
def svg_diff(actual_svg: SVG, expected_svg: SVG):
    drop_whitespace(actual_svg)
    drop_whitespace(expected_svg)
    print(f"A: {pretty_print(actual_svg.toetree())}")
    print(f"E: {pretty_print(expected_svg.toetree())}")
    assert actual_svg.tostring() == expected_svg.tostring()


def run(cmd):
    cmd = tuple(str(c) for c in cmd)
    print("subprocess:", " ".join(cmd))  # very useful on failure
    env = {
        # We may need to find nanoemoji and other pip-installed cli tools
        "PATH": str(Path(shutil.which("nanoemoji")).parent),
        # We may need to find test modules
        "PYTHONPATH": os.pathsep.join((str(Path(__file__).parent),)),
    }
    # Needed for windows CI to function; ref https://github.com/appveyor/ci/issues/1995
    if "SYSTEMROOT" in os.environ:
        env["SYSTEMROOT"] = os.environ["SYSTEMROOT"]

    return subprocess.run(cmd, check=True, env=env)


def run_nanoemoji(args, tmp_dir=None):
    if not tmp_dir:
        tmp_dir = mkdtemp()

    run(
        (
            "nanoemoji",
            "--build_dir",
            str(tmp_dir),
        )
        + tuple(str(a) for a in args)
    )

    assert (tmp_dir / "build.ninja").is_file()

    return tmp_dir


_TEMPORARY_DIRS = set()


def active_temp_dirs():
    return _TEMPORARY_DIRS


def forget_temp_dirs():
    global _TEMPORARY_DIRS
    _TEMPORARY_DIRS = set()
    assert len(active_temp_dirs()) == 0  # this can occur due to local/global confusion


def mkdtemp() -> Path:
    tmp_dir = Path(tempfile.mkdtemp())
    assert tmp_dir not in _TEMPORARY_DIRS
    _TEMPORARY_DIRS.add(tmp_dir)
    return tmp_dir


def cleanup_temp_dirs():
    while _TEMPORARY_DIRS:
        shutil.rmtree(_TEMPORARY_DIRS.pop(), ignore_errors=True)


def bool_flag(name: str, value: bool) -> str:
    result = "--"
    if not value:
        result += "no"
    result += name
    return result
