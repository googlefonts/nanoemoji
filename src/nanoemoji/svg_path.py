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

from typing import Any, Mapping, Optional
import itertools
from fontTools.pens.basePen import AbstractPen, DecomposingPen
from fontTools.pens.transformPen import TransformPen
import pathops
from picosvg.svg_types import SVGPath
from picosvg.svg_transform import Affine2D


_SVG_CMD_TO_PEN_METHOD = {
    "M": "moveTo",
    "L": "lineTo",
    "C": "curveTo",
    "Q": "qCurveTo",
    "Z": "closePath",
}


def draw_svg_path(
    path: SVGPath, pen: AbstractPen, transform: Optional[Affine2D] = None
):
    """Draw SVGPath using a FontTools Segment Pen."""
    if transform is not None:
        pen = TransformPen(pen, transform)

    # In SVG sub-paths are implicitly open when they don't end with "Z"; in FT pens
    # the end of each sub-path must be marked explicitly with either pen.endPath()
    # for open paths or closePath() for closed ones.
    closed = True
    for cmd, args in path.as_cmd_seq():
        if cmd == "M":
            if not closed:
                pen.endPath()
            closed = False

        # pens expect args as 2-tuples; we use the 'grouper' itertools recipe
        # https://docs.python.org/3.8/library/itertools.html#recipes
        assert len(args) % 2 == 0
        points = itertools.zip_longest(*([iter(args)] * 2))

        getattr(pen, _SVG_CMD_TO_PEN_METHOD[cmd])(*points)

        if cmd == "Z":
            closed = True

    if not closed:
        pen.endPath()


class SVGPathPen(DecomposingPen):
    """A FontTools Pen that draws onto a picosvg SVGPath.

    The pen automatically decomposes components using the provided `glyphSet`
    mapping.

    Args:
        glyphSet: a mapping of {glyph_name: glyph} to be used for resolving
            component references when the pen's `addComponent` method is called.
        path: an existing SVGPath to extend with drawing commands. If None, a new
            SVGPath is created by default, accessible with the `path` attribute.
    """

    # addComponent will raise KeyError on missing reference, instead of just warning
    skipMissingComponents = False

    def __init__(
        self,
        glyphSet: Optional[Mapping[str, Any]] = None,
        path: Optional[SVGPath] = None,
    ):
        DecomposingPen.__init__(self, glyphSet or {})
        self.path = path or SVGPath()

    def moveTo(self, pt):
        self.path.M(*pt)

    def lineTo(self, pt):
        self.path.L(*pt)

    def curveTo(self, *points):
        # flatten sequence of point tuples
        self.path.C(*(v for pt in points for v in pt))

    def qCurveTo(self, *points):
        # handle TrueType quadratic splines with implicit on-curve mid-points
        for (control_pt, end_pt) in pathops.decompose_quadratic_segment(points):
            self.path.Q(*control_pt, *end_pt)

    def closePath(self):
        self.path.end()

    def endPath(self):
        pass
