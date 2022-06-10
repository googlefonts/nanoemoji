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
from nanoemoji.glyph_reuse import GlyphReuseCache, ReuseResult
from picosvg.svg_transform import Affine2D
import pytest


# Not try to fully exercise affine_between, just to sanity check things somewhat work
@pytest.mark.parametrize(
    "path_a, path_b, expected_result",
    [
        (
            "M-1,-1 L 0,1 L 1, -1 z",
            "M-2,-2 L 0,2 L 2, -2 z",
            ReuseResult(glyph_name="A", transform=Affine2D.identity().scale(2)),
        ),
        # https://github.com/googlefonts/nanoemoji/issues/313
        (
            "M818.7666015625,133.60003662109375 C818.7666015625,130.28631591796875 816.080322265625,127.5999755859375 812.7666015625,127.5999755859375 C809.4529418945312,127.5999755859375 806.7666015625,130.28631591796875 806.7666015625,133.60003662109375 C806.7666015625,136.9136962890625 809.4529418945312,139.60003662109375 812.7666015625,139.60003662109375 C816.080322265625,139.60003662109375 818.7666015625,136.9136962890625 818.7666015625,133.60003662109375 Z",
            "M1237.5,350 C1237.5,18.629150390625 968.870849609375,-250 637.5,-250 C306.1291198730469,-250 37.5,18.629150390625 37.5,350 C37.5,681.370849609375 306.1291198730469,950 637.5,950 C968.870849609375,950 1237.5,681.370849609375 1237.5,350 Z",
            None,
        ),
    ],
)
def test_glyph_reuse_cache(path_a, path_b, expected_result):
    reuse_cache = GlyphReuseCache(_DEFAULT_CONFIG.reuse_tolerance)
    reuse_cache.add_glyph("A", path_a)
    assert reuse_cache.try_reuse(path_b) == expected_result
