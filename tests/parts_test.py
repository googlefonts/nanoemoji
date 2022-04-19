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

from nanoemoji.parts import ReuseableParts
from picosvg.svg_types import SVGCircle, SVGRect
import pprint
import pytest
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


def check_num_shapes(parts: ReuseableParts, expected_shape_sets: int):
    assert len(parts.shape_sets) == expected_shape_sets, ",".join(
        sorted(str(p) for p in parts.shape_sets.keys())
    )


def test_collects_normalized_shapes():
    shapes = (
        SVGRect(width=2, height=1),
        SVGRect(width=4, height=2),
        SVGCircle(r=2),
    )

    parts = ReuseableParts()
    parts.add(shapes)

    check_num_shapes(parts, 2)


def test_from_svg():
    parts = ReuseableParts.load(locate_test_file("rect.svg"))
    check_num_shapes(parts, 1)


def test_merge():
    shapes1 = (SVGRect(width=2, height=1),)
    shapes2 = (
        SVGRect(width=4, height=2),
        SVGCircle(r=2),
    )

    p1 = ReuseableParts()
    p1.add(shapes1)
    check_num_shapes(p1, 1)

    p2 = ReuseableParts()
    p2.add(shapes2)
    check_num_shapes(p2, 2)

    p1.add(p2)
    check_num_shapes(p1, 2)


def test_file_io():
    parts = ReuseableParts()
    parts.add(locate_test_file("rect.svg"))
    check_num_shapes(parts, 1)

    tmp_dir = mkdtemp()
    tmp_file = tmp_dir / "rect.json"
    tmp_file.write_text(parts.to_json())

    assert parts == ReuseableParts.load(tmp_file)
