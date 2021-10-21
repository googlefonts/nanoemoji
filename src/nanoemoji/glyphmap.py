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
from nanoemoji import codepoints
from pathlib import Path
from typing import NamedTuple, Optional, Tuple


class GlyphMapping(NamedTuple):
    svg_file: Path
    codepoints: Tuple[int, ...]
    glyph_name: str

    def csv_line(self):
        cp_str = ""
        if self.codepoints:
            cp_str = codepoints.string(self.codepoints)
        return f"{self.svg_file}, {self.glyph_name}, {cp_str}"


def load_from(file):
    results = []
    reader = csv.reader(file, skipinitialspace=True)
    for row in reader:
        try:
            svg_file, glyph_name, *cps = row
        except ValueError as e:
            raise ValueError(f"Error parsing {row} from {file}") from e

        svg_file = Path(svg_file)

        if cps and cps != [""]:
            cps = tuple(int(cp, 16) for cp in cps)
        else:
            cps = ()
        results.append(GlyphMapping(svg_file, cps, glyph_name))

    return tuple(results)


def parse_csv(filename):
    with open(filename) as f:
        return load_from(f)
