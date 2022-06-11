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

from nanoemoji.parts import ReusableParts
from nanoemoji.util import only
from picosvg.geometric_types import Rect
from picosvg.svg import SVG
from picosvg import svg_meta
from picosvg.svg_types import SVGCircle, SVGPath, SVGRect
from picosvg.svg_reuse import affine_between
from pathlib import Path
import pprint
import pytest
import re
from test_helper import cleanup_temp_dirs, locate_test_file, mkdtemp


@pytest.fixture(scope="module", autouse=True)
def _cleanup_temporary_dirs():
    # The mkdtemp() docs say the user is responsible for deleting the directory
    # and its contents when done with it. So we use an autouse fixture that
    # automatically removes all the temp dirs at the end of the test module
    yield
    # teardown happens after the 'yield'
    cleanup_temp_dirs()


# BUG? rect(2,1) and rect(1,2) do NOT normalize the same.
# TODO we get pointless precision, e.g. 1.2000000000000002


def _svg_commands(path: str) -> str:
    print(path)
    svg_cmds = "".join(svg_meta.cmds())
    return re.sub(f"[^{svg_cmds}]+", "", path)


def check_num_shapes(parts: ReusableParts, expected_shape_sets: int):
    assert len(parts.shape_sets) == expected_shape_sets, ",".join(
        sorted(str(p) for p in parts.shape_sets.keys())
    )


def _from_svg(svg, view_box=None) -> ReusableParts:
    if isinstance(svg, str):
        svg = SVG.fromstring(svg)
    elif isinstance(svg, Path):
        svg = SVG.parse(svg)
    if view_box is None:
        view_box = svg.view_box()
    parts = ReusableParts(view_box=view_box)
    parts.add(svg)
    return parts


def test_add_svg():
    parts = _from_svg(
        """
        <svg viewBox="0 0 10 10" xmlns="http://www.w3.org/2000/svg"
             xmlns:xlink="http://www.w3.org/1999/xlink">
          <rect x="2" y="2" width="6" height="2" fill="blue" />
          <rect x="4" y="4" width="6" height="2" fill="blue" opacity="0.8" />
        </svg>
        """
    )
    check_num_shapes(parts, 1)


def test_collects_normalized_shapes():
    parts = _from_svg(
        """
        <svg viewBox="0 0 10 10" xmlns="http://www.w3.org/2000/svg">
          <rect width="2" height="1"/>
          <rect width="4" height="2" y="1.5"/>
          <circle cx="5" cy="5" r="2"/>
        </svg>
        """
    )

    check_num_shapes(parts, 2)


def test_simple_merge():
    p1 = _from_svg(
        """
        <svg viewBox="0 0 20 20" xmlns="http://www.w3.org/2000/svg">
          <rect width="2" height="1"/>
        </svg>
        """
    )
    check_num_shapes(p1, 1)

    p2 = _from_svg(
        """
        <svg viewBox="0 0 10 10" xmlns="http://www.w3.org/2000/svg">
          <rect width="4" height="2" y="1.5"/>
          <circle r="2"/>
        </svg>
        """
    )
    check_num_shapes(p2, 2)

    p1.add(p2)
    check_num_shapes(p1, 2)


def test_file_io():
    parts = _from_svg(locate_test_file("rect.svg"))
    check_num_shapes(parts, 1)

    tmp_dir = mkdtemp()
    tmp_file = tmp_dir / "rect.json"
    tmp_file.write_text(parts.to_json())

    assert parts == ReusableParts.loadjson(tmp_file), parts.to_json()


# Note that this is not meant to be the primary test of reuse, that's in
# picosvg. This just checks we use those capabilities in the expected manner.
@pytest.mark.parametrize(
    "svg",
    [
        SVG.fromstring(
            """
            <svg viewBox="0 0 10 10" xmlns="http://www.w3.org/2000/svg">
              <rect width="2" height="1"/>
              <rect width="4" height="2" y="1.5"/>
            </svg>
            """
        ).topicosvg(),
        # https://github.com/googlefonts/nanoemoji/issues/415 arc normalization
        SVG.fromstring(
            """
            <svg viewBox="0 0 10 10" xmlns="http://www.w3.org/2000/svg">
              <circle r="1"/>
              <circle r="2"/>
            </svg>
            """
        ).topicosvg(),
    ],
)
def test_reuse_finds_single_donor(svg):
    parts = _from_svg(svg.tostring())

    # There should be one shape used to create all the others
    maybe_reuses = [parts.try_reuse(s.as_path()) for s in svg.shapes()]
    assert all(ri is not None for ri in maybe_reuses), "All shapes should have results"
    scale_up = {
        ri for ri in maybe_reuses if not all(v <= 1.0 for v in ri.transform.getscale())
    }
    assert not scale_up, f"Should prefer to scale big to little {scale_up}"
    assert (
        len({ri.shape for ri in maybe_reuses}) == 1
    ), f"{maybe_reuses} should all reuse the same shape"


# Feed in two identical svgs, just one of them multiplies viewbox and coords by 10
def test_reuse_with_inconsistent_square_viewbox():
    little = locate_test_file("rect.svg")
    big = locate_test_file("rect_10x.svg")

    r1 = _from_svg(little)
    assert r1.view_box == Rect(0, 0, 10, 10)
    r1.add(_from_svg(big))
    r1.compute_donors()

    r2 = _from_svg(big)
    assert r2.view_box == Rect(0, 0, 100, 100)
    r2.add(_from_svg(little))
    r2.compute_donors()

    check_num_shapes(r1, 1)
    check_num_shapes(r2, 1)
    assert only(r1.shape_sets.values()) == {
        "M2,2 L8,2 L8,4 L2,4 L2,2 Z",
        "M4,4 L10,4 L10,6 L4,6 L4,4 Z",
    }, "There should be 2 (not 4) shapes after scaled merge. r1 should use the little viewbox."
    assert only(r2.shape_sets.values()) == {
        "M20,20 L80,20 L80,40 L20,40 L20,20 Z",
        "M40,40 L100,40 L100,60 L40,60 L40,40 Z",
    }, "There should be 2 (not 4) shapes after scaled merge. r2 should use the big viewbox."


def test_arcs_become_cubics():
    parts = _from_svg(
        """
        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10">
          <defs/>
          <path d="M2,0 A2 2 0 1 1 -2,0 A2 2 0 1 1 2,0 Z"/>
        </svg>
        """
    )

    norm, path = only(parts.shape_sets.items())
    path = only(path)
    assert (_svg_commands(norm), _svg_commands(path)) == (
        "Mccccz",
        "MCCCCZ",
    ), f"Wrong command types\nnorm {norm}\npath {path}"


# scaling turns arcs into cubics
# we need them to reuse regardless
def test_scaled_merge_arcs_to_cubics():
    parts = _from_svg(locate_test_file("circle_10x.svg"))
    part2 = _from_svg(locate_test_file("circle.svg"))
    assert parts.view_box == Rect(0, 0, 100, 100)
    assert part2.view_box == Rect(0, 0, 10, 10)
    parts.add(part2)

    assert len(parts.shape_sets) == 1, parts.to_json()
    norm, paths = only(parts.shape_sets.items())
    path_cmds = tuple(_svg_commands(p) for p in paths)
    assert (_svg_commands(norm),) + path_cmds == (
        "Mccccz",
        "MCCCCZ",
        "MCCCCZ",
    ), f"Path damaged\nnorm {norm}\npaths {paths}"


def _start_at_origin(path):
    cmd, args = next(iter(path))
    assert cmd == "M"
    x, y = args
    return path.move(-x, -y)


# SVGs with varied width that contains squares should push squares
# into the part store, not get mangled into rectangles.
def test_squares_stay_squares():
    parts = ReusableParts(view_box=Rect(0, 0, 10, 10))

    parts.add(SVG.parse(locate_test_file("square_vbox_narrow.svg")))
    parts.add(SVG.parse(locate_test_file("square_vbox_square.svg")))
    parts.add(SVG.parse(locate_test_file("square_vbox_narrow.svg")))

    # Every square should have normalized the same
    assert len(parts.shape_sets) == 1, parts.to_json()

    paths = only(parts.shape_sets.values())

    paths = [_start_at_origin(SVGPath(d=p)).relative(inplace=True) for p in paths]
    assert {p.d for p in paths} == {
        "M0,0 l3,0 l0,3 l-3,0 l0,-3 z"
    }, "The square should remain 3x3; converted to relative and starting at 0,0 they should be identical"
