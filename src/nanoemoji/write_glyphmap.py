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

"""Default glyphmap writer. Writes rows like:


picosvg/clipped/emoji_u270d_1f3fb.svg, bitmap/emoji_u270d_1f3fb.png, g_270d_1f3fb, 270d, 1f3fb

The first two columns represent respectively the SVG and bitmap filenames; either can be
left empty if the font is vector- or bitmap-only.
The third column is the UFO/PostScript glyph name, and it's required.
The fourth and the remaining columns are optional, and contain the Unicode codepoints
as hexadecimal digits; a single codepoint gets added to the cmap, more than one produce
a GSUB ligature, no codepoint leaves the glyph unmapped.
"""


import enum
from absl import app
from absl import flags
from nanoemoji.glyph import glyph_name
from nanoemoji.glyphmap import GlyphMapping
from nanoemoji import codepoints
from nanoemoji import util
from pathlib import Path
from typing import Iterator, Sequence, Tuple

FLAGS = flags.FLAGS

flags.DEFINE_string("output_file", "-", "Output filename ('-' means stdout)")


class InputFileSuffix(enum.Enum):
    SVG = ".svg"
    PNG = ".png"


def _glyphmappings(input_files: Sequence[str]) -> Iterator[GlyphMapping]:
    # group .svg and/or .png files with the same filename stem
    sources_by_stem = {}
    suffix_index = {InputFileSuffix.SVG: 0, InputFileSuffix.PNG: 1}
    for filename in input_files:
        input_file = Path(filename)
        i = suffix_index[InputFileSuffix(input_file.suffix)]
        sources_by_stem.setdefault(input_file.stem, [None, None])[i] = input_file
    for source_stem, files in sources_by_stem.items():
        cps = tuple(codepoints.from_filename(source_stem))
        yield GlyphMapping(*files, cps, glyph_name(cps))


def main(argv):
    input_files = util.expand_ninja_response_files(argv[1:])
    with util.file_printer(FLAGS.output_file) as print:
        for gm in _glyphmappings(input_files):
            # filename(s), glyph_name, codepoint(s)
            print(gm.csv_line())


if __name__ == "__main__":
    app.run(main)
