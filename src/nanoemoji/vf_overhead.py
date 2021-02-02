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

"""Helps estimate overhead due to VF offsets."""

from absl import app
from fontTools.colorLib.builder import LayerV1ListBuilder
from fontTools import ttLib
from fontTools.ttLib.tables import otTables as ot
from nanoemoji import colr_traverse
from pathlib import Path

# VarIdx costs 4 bytes in every Var<something>
# ColorIndex costs 4: alpha
# ColorStop costs 8: 4 (stopOffset) + 4 (ColorIndex)
# ColorLine costs #stops * 8 : ColorStop
# Affine2x3 costs 24: 4 per field
def _overhead_color_line(color_line):
    return 8 * len(color_line.ColorStop)

def _overhead_gradient(color_line, num_fields):
    return _overhead_color_line(color_line) + 4 * num_fields

_OVERHEAD = {
    ot.Paint.Format.PaintColrLayers: lambda p: 0,

    ot.Paint.Format.PaintSolid: lambda p: 4,
    ot.Paint.Format.PaintLinearGradient: lambda p: _overhead_gradient(p.ColorLine, 6),
    ot.Paint.Format.PaintRadialGradient: lambda p: _overhead_gradient(p.ColorLine, 6),

    ot.Paint.Format.PaintGlyph: lambda p: 0,
    ot.Paint.Format.PaintColrGlyph: lambda p: 0,

    ot.Paint.Format.PaintTransform: lambda p: 6 * 4,
    ot.Paint.Format.PaintTranslate: lambda p: 2 * 4,
    ot.Paint.Format.PaintRotate: lambda p: 3 * 4,
    ot.Paint.Format.PaintSkew: lambda p: 4 * 4,
    ot.Paint.Format.PaintComposite: lambda p: 0,
}


def _count_overhead(colr):
    total_overhead = 0
    visited = set()
    list_builder = LayerV1ListBuilder()

    def _callback(paint):
        overhead = 0
        paint_tuple = list_builder._paint_tuple(paint)
        seen = paint_tuple in visited
        if not seen:
            visited.add(paint_tuple)
            overhead = _OVERHEAD[paint.Format](paint)
        nonlocal total_overhead
        total_overhead += overhead

    for base_glyph in colr.table.BaseGlyphV1List.BaseGlyphV1Record:
        colr_traverse.traverse(colr, base_glyph.Paint, _callback)

    return total_overhead


def main(argv):
    if len(argv) != 2:
        raise ValueError("Only expected non-flag is font file")
    font = ttLib.TTFont(argv[1])

    file_size = Path(argv[1]).stat().st_size
    colr_size = len(font.reader["COLR"])
    varidx_size = _count_overhead(font["COLR"])
    pct_colr = 100. * varidx_size / colr_size
    pct_file = 100. * varidx_size / file_size

    print(f"{varidx_size} / {colr_size} bytes ({pct_colr:.1f}%) of the COLR table are variation indices")
    print(f"{varidx_size} / {file_size} bytes ({pct_file:.1f}%) of the font file are variation indices")



if __name__ == "__main__":
    app.run(main)
