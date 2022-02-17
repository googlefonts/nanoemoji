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


emoji_u270d_1f3fb, g_270d_1f3fb, "270d,1f3fb"

"""


from absl import app
from absl import flags
from nanoemoji.glyph import glyph_name
from nanoemoji.glyphmap import GlyphMapping
from nanoemoji import codepoints
from nanoemoji import features
from nanoemoji import util
from pathlib import Path
from typing import Iterator, Sequence, Tuple

FLAGS = flags.FLAGS

flags.DEFINE_string("output_file", "-", "Output filename ('-' means stdout)")


def _glyphmappings(source_names: Sequence[str]) -> Iterator[GlyphMapping]:
    yield from (
        GlyphMapping(source_stem, cps, glyph_name(cps))
        for source_stem, cps in zip(
            (Path(name).stem for name in source_names),
            (codepoints.from_filename(name) for name in source_names),
        )
    )


def main(argv):
    source_names = Path(argv[1]).read_text().splitlines()
    with util.file_printer(FLAGS.output_file) as print:
        for gm in _glyphmappings(source_names):
            # filename(s), glyph_name, codepoint(s)
            print(gm.csv_line())


if __name__ == "__main__":
    app.run(main)
