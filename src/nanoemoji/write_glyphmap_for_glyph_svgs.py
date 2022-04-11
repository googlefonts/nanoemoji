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

"""Generates a glyphmap for svgs named by glyph id."""
from absl import app
from absl import flags
from absl import logging
from fontTools import ttLib
from nanoemoji.glyphmap import GlyphMapping
from nanoemoji import util
from pathlib import Path


FLAGS = flags.FLAGS

flags.DEFINE_string("output_file", "-", "Output filename ('-' means stdout)")
flags.DEFINE_bool("bitmaps", False, "True if bitmaps should be included in glyphmap")


def main(argv):
    input_files = util.expand_ninja_response_files(argv[1:])
    del argv
    source_font = util.only(input_files, lambda a: a.endswith(".ttf"))

    glyph_order = ttLib.TTFont(source_font).getGlyphOrder()

    input_files = sorted(
        (Path(f) for f in input_files if f != source_font),
        key=lambda f: f.stem,
        reverse=True,
    )

    with util.file_printer(FLAGS.output_file) as print:
        while input_files:
            svg_file = input_files.pop()
            assert svg_file.suffix in {".png", ".svg"}, f"What is {svg_file}"
            bitmap_file = None
            if svg_file.suffix == ".png":
                bitmap_file = svg_file
                svg_file = input_files.pop()
                assert svg_file.suffix == ".svg"
                assert int(svg_file.stem) == int(
                    bitmap_file.stem
                ), f"Mismatched {svg_file}, {bitmap_file}"

            print(
                GlyphMapping(
                    svg_file=svg_file,
                    bitmap_file=bitmap_file,
                    codepoints=(),
                    glyph_name=glyph_order[int(svg_file.stem)],
                ).csv_line()
            )


if __name__ == "__main__":
    app.run(main)
