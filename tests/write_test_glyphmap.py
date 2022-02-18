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

"""Test glyphmap writer. Writes a glyphmap where every second glyph gets no codepoints.

"""


from absl import app
from absl import flags
from nanoemoji.glyphmap import GlyphMapping
from nanoemoji import codepoints
from nanoemoji import util
from pathlib import Path
from typing import Iterator, Sequence, Tuple

FLAGS = flags.FLAGS

flags.DEFINE_string("output_file", "-", "Output filename ('-' means stdout)")


def _glyphmappings(input_files: Sequence[str]) -> Iterator[GlyphMapping]:
    yield from (
        GlyphMapping(
            svg_file=Path(input_file),
            bitmap_file=None,
            codepoints=(
                () if idx % 2 == 1 else codepoints.from_filename(Path(input_file).name)
            ),
            glyph_name=f"custom_name_{idx}",
        )
        for idx, input_file in enumerate(input_files)
    )


def main(argv):
    input_files = util.expand_ninja_response_files(argv[1:])
    with util.file_printer(FLAGS.output_file) as print:
        for gm in _glyphmappings(input_files):
            # filename(s), glyph_name, codepoint(s)
            print(gm.csv_line())


if __name__ == "__main__":
    app.run(main)
