# Copyright 2021 Google LLC
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

from fontTools.ttLib.tables import otTables as ot
from nanoemoji.paint import Color, _decompose_uniform_transform
from nanoemoji.paint import *
import pytest


@pytest.mark.parametrize(
    "paint, colors, expected_ufo_paint",
    [
        (
            PaintSolid(),
            [Color.fromstring("black")],
            {
                "Format": ot.PaintFormat.PaintSolid,
                "PaletteIndex": 0,
                "Alpha": 1,
            },
        ),
    ],
)
def test_to_ufo_paint(paint, colors, expected_ufo_paint):
    assert paint.to_ufo_paint(colors) == expected_ufo_paint


@pytest.mark.parametrize(
    "input_point, paint, expected_point",
    [
        # No modification should occur
        (
            Point(1, 1),
            PaintSolid(),
            Point(1, 1),
        ),
        # Rotate 1,0 90 degrees around origin
        (
            Point(1, 0),
            PaintRotate(
                paint=PaintSolid(),
                angle=90,
            ),
            Point(0, 1),
        ),
        # Rotate 1,0 90 degrees around 2,1
        (
            Point(1, 0),
            PaintRotateAroundCenter(
                paint=PaintSolid(),
                angle=90,
                center=Point(2, 0),
            ),
            Point(2, -1),
        ),
        # x-skew 0,1 45 degrees around origin
        (
            Point(0, 1),
            PaintSkew(
                paint=PaintSolid(),
                xSkewAngle=45,
                ySkewAngle=0,
            ),
            Point(-1, 1),
        ),
        # 2-skew 0, 1 45 degrees around (0, 1)
        (
            Point(0, 1),
            PaintSkewAroundCenter(
                paint=PaintSolid(),
                xSkewAngle=45,
                ySkewAngle=0,
                center=Point(0, 1),
            ),
            Point(0, 1),
        ),
    ],
)
def test_gettransform(input_point, paint, expected_point):
    assert paint.gettransform().map_point(input_point).round(6) == expected_point


@pytest.mark.parametrize(
    "transform, target, expected_result",
    [
        # Nop
        (
            Affine2D.identity(),
            PaintGlyph(glyph="A Glyph", paint=PaintSolid()),
            PaintGlyph(glyph="A Glyph", paint=PaintSolid()),
        ),
        # Int16 translation (expected to be typical case)
        (
            Affine2D.fromstring("translate(-5, 10)"),
            PaintGlyph(glyph="A Glyph", paint=PaintSolid()),
            PaintTranslate(
                paint=PaintGlyph(glyph="A Glyph", paint=PaintSolid()),
                dx=-5,
                dy=10,
            ),
        ),
        # Non-Int16 translation
        (
            Affine2D.fromstring("translate(-5.5, 10)"),
            PaintGlyph(glyph="A Glyph", paint=PaintSolid()),
            PaintTransform(
                paint=PaintGlyph(glyph="A Glyph", paint=PaintSolid()),
                transform=(1, 0, 0, 1, -5.5, 10),
            ),
        ),
        # Uniform scaling
        (
            Affine2D.fromstring("scale(1.75)"),
            PaintGlyph(glyph="A Glyph", paint=PaintSolid()),
            PaintScaleUniform(
                paint=PaintGlyph(glyph="A Glyph", paint=PaintSolid()),
                scale=1.75,
            ),
        ),
        # Non-uniform scaling
        (
            Affine2D.fromstring("scale(1.75, 1.5)"),
            PaintGlyph(glyph="A Glyph", paint=PaintSolid()),
            PaintScale(
                paint=PaintGlyph(glyph="A Glyph", paint=PaintSolid()),
                scaleX=1.75,
                scaleY=1.5,
            ),
        ),
        # Scaling unsafe for f2dot14
        (
            Affine2D.fromstring("scale(3.1)"),
            PaintGlyph(glyph="A Glyph", paint=PaintSolid()),
            PaintTransform(
                paint=PaintGlyph(glyph="A Glyph", paint=PaintSolid()),
                transform=(3.1, 0, 0, 3.1, 0, 0),
            ),
        ),
        # PaintScaleAroundCenter
        (
            Affine2D(0.5, 0, 0, 1.5, 30, 40),
            PaintGlyph(glyph="A Glyph", paint=PaintSolid()),
            PaintScaleAroundCenter(
                paint=PaintGlyph(glyph="A Glyph", paint=PaintSolid()),
                scaleX=0.5,
                scaleY=1.5,
                center=Point(60, -80),
            ),
        ),
        # PaintScaleAroundCenter whilst avoiding / 0
        (
            Affine2D(1, 0, 0, 0.5, 0, 100),
            PaintGlyph(glyph="A Glyph", paint=PaintSolid()),
            PaintScaleAroundCenter(
                paint=PaintGlyph(glyph="A Glyph", paint=PaintSolid()),
                scaleX=1,
                scaleY=0.5,
                center=Point(0, 200),
            ),
        ),
        # Do NOT PaintScaleAroundCenter when translation isn't ~int
        (
            Affine2D(0.45, 0, 0, 1.5, 30, 40),
            PaintGlyph(glyph="A Glyph", paint=PaintSolid()),
            PaintTransform(
                paint=PaintGlyph(glyph="A Glyph", paint=PaintSolid()),
                transform=(0.45, 0, 0, 1.5, 30, 40),
            ),
        ),
        # PaintScaleUniformAroundCenter
        (
            Affine2D(0.75, 0, 0, 0.75, -20, 40),
            PaintGlyph(glyph="A Glyph", paint=PaintSolid()),
            PaintScaleUniformAroundCenter(
                paint=PaintGlyph(glyph="A Glyph", paint=PaintSolid()),
                scale=0.75,
                center=Point(-80, 160),
            ),
        ),
    ],
)
def test_transformed(transform, target, expected_result):
    assert transformed(transform, target) == expected_result


@pytest.mark.parametrize(
    "transform, expected_uniform_transform, expected_remaining_transform",
    [
        (
            Affine2D(2, 0, 0, 1, 0, 0),
            Affine2D(2, 0, 0, 2, 0, 0),
            Affine2D(1, 0, 0, 0.5, 0, 0),
        ),
        (
            Affine2D(8, 0, 0, -8, 0, 1024),
            Affine2D(8, 0, 0, -8, 0, 1024),
            Affine2D(1, 0, 0, 1, 0, 0),
        ),
        (
            Affine2D.fromstring("rotate(-90) translate(50, -100)"),
            Affine2D(1, 0, 0, 1, 50, -100),
            Affine2D(0, -1.0, 1.0, 0, 0, 0),
        ),
        (
            Affine2D.fromstring("rotate(90) scale(2)"),
            Affine2D(2, 0, 0, 2, 0, 0),
            Affine2D(0, 1.0, -1.0, 0, 0, 0),
        ),
        (
            Affine2D.fromstring("translate(50, -100) scale(2) rotate(90)"),
            Affine2D(2, 0, 0, 2, -100, -50),
            Affine2D(0, 1.0, -1.0, 0, 0, 0),
        ),
    ],
)
def test_decompose_uniform_transform(
    transform, expected_uniform_transform, expected_remaining_transform
):
    assert _decompose_uniform_transform(transform) == (
        expected_uniform_transform,
        expected_remaining_transform,
    )
