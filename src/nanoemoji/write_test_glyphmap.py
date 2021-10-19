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
from nanoemoji import features
from nanoemoji import util
from pathlib import Path
from typing import Sequence, Tuple

FLAGS = flags.FLAGS

flags.DEFINE_string("output_file", "-", "Output filename ('-' means stdout)")


def _glyphmappings(svg_files: Sequence[str]) -> Tuple[GlyphMapping]:
    result = []
    for idx, (svg_file, cps) in enumerate(
        zip(svg_files, tuple(codepoints.from_filename(Path(f).name) for f in svg_files))
    ):
        if idx % 2 == 1:
            cps = ()
        result.append(GlyphMapping(Path(svg_file), cps, f"custom_name_{idx}"))
    return tuple(result)


def main(argv):
    with util.file_printer(FLAGS.output_file) as print:
        for gm in _glyphmappings(argv[1:]):
            # filename, codepoint(s), glyph name
            print(gm.csv_line())


if __name__ == "__main__":
    app.run(main)
