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

from nanoemoji import color_glyph
from picosvg.svg import SVG
from fontTools import ttLib
from picosvg.geometric_types import Rect




def _emsquare_to_viewbox(upem: int, view_box: Rect):
    if view_box != Rect(0, 0, view_box.w, view_box.w):
        raise ValueError('We simply must have a BOX from 0,0')
    return map_viewbox_to_emsquare(Rect(0, 0, upem, upem), view_box.w)

def colr_to_svg(view_box: Rect, ttfont: ttLib.TTFont) -> SVG:
  """For testing only, don't use for real!"""
  # Coordinate scaling
  affine = _emsquare_to_viewbox(ttfont['head'].unitsPerEm, view_box)

  # Viewbox
  # Gradient definitions
  # Paths

  return SVG.fromstring('<svg/>')