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

"""Helps with traversal of a COLR glyph graph."""


from fontTools.ttLib.tables import otTables as ot


_LEAVES = {
    ot.Paint.Format.PaintSolid,
    ot.Paint.Format.PaintLinearGradient,
    ot.Paint.Format.PaintRadialGradient,
    #ot.Paint.Format.PaintSweepGradient,
}

_HAS_PAINT = {
    ot.Paint.Format.PaintGlyph,
    ot.Paint.Format.PaintTransform,
    ot.Paint.Format.PaintTranslate,
    ot.Paint.Format.PaintRotate,
    ot.Paint.Format.PaintSkew,
}


def _only(seq):
    seq = tuple(seq)
    if len(seq) != 1:
        raise ValueError(f"Need 1 entry, got {len(seq)}")
    return seq[0]


def _base_glyphs(colr, filter_fn):
    for base_glyph in colr.table.BaseGlyphV1List.BaseGlyphV1Record:
        if filter_fn(base_glyph):
            yield base_glyph


def _children(colr, paint: ot.Paint):
    if paint.Format in _LEAVES:
        return []

    if paint.Format == ot.Paint.Format.PaintColrLayers:
        return colr.table.LayerV1List.Paint[
            paint.FirstLayerIndex : paint.FirstLayerIndex + paint.NumLayers
        ]

    if paint.Format == ot.Paint.Format.PaintColrGlyph:
        return [_only(_base_glyphs(colr, lambda g: g.BaseGlyph == paint.Glyph)).Paint]

    if paint.Format in _HAS_PAINT:
        return [paint.Paint]

    if paint.Format == ot.Paint.Format.PaintComposite:
        return [paint.SourcePaint, paint.BackdropPaint]

    raise ValueError(f"Unrecognized format {paint.Format}")


def traverse(colr, root: ot.Paint, callback_fn):
    frontier = [root]
    while frontier:
        current = frontier.pop(0)
        callback_fn(current)

        frontier.extend(_children(colr, current))
