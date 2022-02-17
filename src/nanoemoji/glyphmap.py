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
from io import StringIO
from pathlib import Path
from typing import NamedTuple, Tuple


class GlyphMapping(NamedTuple):
    source_stem: str  # source filename w/o suffix, i.e. Path(source_file).stem
    codepoints: Tuple[int, ...]
    glyph_name: str

    def csv_line(self) -> str:
        row = [self.source_stem, self.glyph_name]
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
            source_stem, glyph_name, *cps = row
        except ValueError as e:
            raise ValueError(f"Error parsing {row} from {file}") from e

        if cps and cps != [""]:
            cps = tuple(int(cp, 16) for cp in cps)
        else:
            cps = ()
        results.append(GlyphMapping(source_stem, cps, glyph_name))

    return tuple(results)


def parse_csv(filename) -> Tuple[GlyphMapping]:
    with open(filename) as f:
        return load_from(f)
