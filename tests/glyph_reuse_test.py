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


from nanoemoji.config import _DEFAULT_CONFIG
from nanoemoji.glyph_reuse import GlyphReuseCache
from nanoemoji.parts import as_shape, ReuseResult, ReusableParts
from picosvg.geometric_types import Rect
from picosvg.svg import SVG
from picosvg.svg_transform import Affine2D
from picosvg.svg_types import SVGPath
import pytest


def _svg(view_box, *paths):
    raw_svg = f'<svg viewBox="{" ".join(str(v) for v in view_box)}" xmlns="http://www.w3.org/2000/svg">\n'
    for path in paths:
        raw_svg += f'  <path d="{path}" />\n'
    raw_svg += "</svg>"
    print(raw_svg)
    return SVG.fromstring(raw_svg)


# https://github.com/googlefonts/nanoemoji/issues/313: fixed by ReusableParts.
# Previously if small was seen first no solution.
def test_small_then_large_circle():

    small_circle = "M818.7666015625,133.60003662109375 C818.7666015625,130.28631591796875 816.080322265625,127.5999755859375 812.7666015625,127.5999755859375 C809.4529418945312,127.5999755859375 806.7666015625,130.28631591796875 806.7666015625,133.60003662109375 C806.7666015625,136.9136962890625 809.4529418945312,139.60003662109375 812.7666015625,139.60003662109375 C816.080322265625,139.60003662109375 818.7666015625,136.9136962890625 818.7666015625,133.60003662109375 Z"
    large_circle = "M1237.5,350 C1237.5,18.629150390625 968.870849609375,-250 637.5,-250 C306.1291198730469,-250 37.5,18.629150390625 37.5,350 C37.5,681.370849609375 306.1291198730469,950 637.5,950 C968.870849609375,950 1237.5,681.370849609375 1237.5,350 Z"

    view_box = Rect(0, 0, 1024, 1024)
    svg = _svg(
        view_box,
        # small circle, encountered first
        small_circle,
        # large circle, encountered second
        large_circle,
    )

    parts = ReusableParts(_DEFAULT_CONFIG.reuse_tolerance, view_box=view_box)
    parts.add(svg)
    parts.compute_donors()

    assert (
        len(parts.shape_sets) == 1
    ), f"Did not normalize the same :( \n{parts.to_json()}"

    # should both have a solution
    solutions = (
        parts.try_reuse(SVGPath(d=small_circle)),
        parts.try_reuse(SVGPath(d=large_circle)),
    )
    assert all(s is not None for s in solutions), parts.to_json()

    # exactly one should have identity, the other ... not
    assert (
        len([s for s in solutions if s.transform.almost_equals(Affine2D.identity())])
        == 1
    ), parts.to_json()
    assert (
        len(
            [s for s in solutions if not s.transform.almost_equals(Affine2D.identity())]
        )
        == 1
    ), parts.to_json()


# Not try to fully exercise affine_between, just to sanity check things somewhat work
@pytest.mark.parametrize(
    "path_a, path_b, expected_result",
    [
        (
            "M-2,-2 L0,2 L2,-2 z",
            "M-1,-1 L0,1 L1,-1 z",
            ReuseResult(
                transform=Affine2D.identity().scale(0.5),
                shape=as_shape(SVGPath(d="M-2,-2 L0,2 L2,-2 z")),
            ),
        ),
    ],
)
def test_glyph_reuse_cache(path_a, path_b, expected_result):
    view_box = Rect(0, 0, 10, 10)
    svg = _svg(
        view_box,
        path_a,
        path_b,
    )

    parts = ReusableParts(_DEFAULT_CONFIG.reuse_tolerance, view_box=view_box)
    parts.add(svg)
    reuse_cache = GlyphReuseCache(parts)
    reuse_cache.set_glyph_for_path("A", path_a)
    reuse_cache.set_glyph_for_path("B", path_b)

    assert reuse_cache.try_reuse(path_b, view_box) == expected_result
