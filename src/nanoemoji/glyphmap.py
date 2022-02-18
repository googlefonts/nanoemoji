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

import csv
from dataclasses import dataclass
from io import StringIO
from pathlib import Path
from typing import NamedTuple, Optional, Tuple


@dataclass(frozen=True)
class GlyphMapping:
    # One of the two paths can be set to None, but at least one is required
    svg_file: Optional[Path]
    bitmap_file: Optional[Path]
    codepoints: Tuple[int, ...]
    glyph_name: str

    def __post_init__(self):
        if not any((self.svg_file, self.bitmap_file)):
            raise ValueError("At least one of svg or bitmap filename is required")

    def csv_line(self) -> str:
        row = [self.svg_file or "", self.bitmap_file or "", self.glyph_name]
        if self.codepoints:
            row.extend(f"{c:04x}" for c in self.codepoints)
        else:
            row.append("")
        # Use a csv.writer instead of ",".join() so we escape commas in file/glyph names
        f = StringIO()
        writer = csv.writer(f, lineterminator="")
        writer.writerow(row)
        return f.getvalue()


def load_from(file) -> Tuple[GlyphMapping]:
    results = []
    reader = csv.reader(file, skipinitialspace=True)
    for row in reader:
        try:
            svg_filename, bitmap_filename, glyph_name, *cps = row
        except ValueError as e:
            raise ValueError(f"Error parsing {row} from {file}") from e

        svg_file = None if not svg_filename else Path(svg_filename)
        bitmap_file = None if not bitmap_filename else Path(bitmap_filename)

        if cps and cps != [""]:
            cps = tuple(int(cp, 16) for cp in cps)
        else:
            cps = ()
        results.append(GlyphMapping(svg_file, bitmap_file, cps, glyph_name))

    return tuple(results)


def parse_csv(filename) -> Tuple[GlyphMapping]:
    with open(filename) as f:
        return load_from(f)
