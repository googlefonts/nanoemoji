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

"""Helpers for dealing with COLR."""


from fontTools.ttLib.tables import otTables as ot
from fontTools import ttLib
from typing import Iterable


def paints_of_type(
    font: ttLib.TTFont, paint_format: ot.PaintFormat
) -> Iterable[ot.Paint]:
    result = []

    def _callback(paint):
        if paint.Format == paint_format:
            result.append(paint)

    colr_table = font["COLR"].table
    for record in colr_table.BaseGlyphList.BaseGlyphPaintRecord:
        record.Paint.traverse(colr_table, _callback)

    return tuple(result)
