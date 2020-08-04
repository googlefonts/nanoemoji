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

import io
import difflib
import os
import re
import sys
from lxml import etree
from nanoemoji import codepoints
from nanoemoji import write_fea
from nanoemoji import write_font
from picosvg.svg import SVG
import pytest
import tempfile


def locate_test_file(filename):
    return os.path.join(os.path.dirname(__file__), filename)


def picosvg(filename, locate=False):
    if locate:
        filename = locate_test_file(filename)
    return SVG.parse(filename).topicosvg()


def color_font_config(color_format, svgs, output_format, keep_glyph_names=True):
    svgs = [locate_test_file(s) for s in svgs]
    fea_file = os.path.join(tempfile.gettempdir(), "test.fea")
    rgi_seqs = [codepoints.from_filename(f) for f in svgs]
    with open(fea_file, "w") as f:
        f.write(write_fea._generate_fea(rgi_seqs))

    return (
        write_font.ColorFontConfig(
            upem=100,
            family="UnitTest",
            color_format=color_format,
            output_format=output_format,
            fea_file=fea_file,
            keep_glyph_names=keep_glyph_names,
        ),
        [
            write_font.InputGlyph(os.path.relpath(svg), (0xE000 + idx,), picosvg(svg))
            for idx, svg in enumerate(svgs)
        ],
    )


def _save_actual_ttx(expected_ttx, ttx_content):
    tmp_file = f"/tmp/{expected_ttx}"
    with open(tmp_file, "w") as f:
        f.write(ttx_content)
    return tmp_file


def assert_expected_ttx(svgs, ttfont, expected_ttx):
    actual_ttx = io.StringIO()
    # Timestamps inside files #@$@#%@#
    # Use os-native line separators so we can run difflib.
    ttfont.saveXML(
        actual_ttx,
        newlinestr=os.linesep,
        skipTables=["head", "hhea", "maxp", "name", "post", "OS/2"],
    )

    # Elide ttFont attributes because ttLibVersion may change
    actual = re.sub(r'\s+ttLibVersion="[^"]+"', "", actual_ttx.getvalue())

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
