# Copyright 2020 Google LLC
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

"""Writes an html file suitable to screenshot for a single font glyph"""


from absl import app
from absl import flags
from nanoemoji import codepoints, util
from pathlib import Path
import textwrap


FLAGS = flags.FLAGS

flags.DEFINE_string("output_file", "-", "Output filename ('-' means stdout)")
flags.DEFINE_integer("resolution", None, "Resolution in px")


def main(argv):
    assert len(argv) == 3
    font_file = Path(argv[1]).name
    activation = "".join(
        f"&#x{cp:04x};" for cp in codepoints.from_filename(Path(argv[2]).name)
    )
    with util.file_printer(FLAGS.output_file) as print:
        # replace rather than f-string because the template contains js-interpolations
        # and double-interpolated strings make my head hurt
        print(
            textwrap.dedent(
                """
            <!DOCTYPE html>
            <script>
                let t0 = performance.now();
            </script>
            <style>
                @font-face {
                    font-family: "TestFont";
                    src: url("FONT_LOCATION");
                    font-display: block;
                }
                * {
                    margin: 0;
                    overflow: hidden;
                    font-family: "TestFont";
                }
            </style>
            <span id="glyph" style="font-size: 16em;">ACTIVATION</span>
            <script>
                window.addEventListener("load", resizeGlyph, false);

                function resizeGlyph(e) {
                  
                  console.log("load", performance.now() - t0, "ms");

                  let glyph = document.getElementById("glyph");

                  // try to hit target height by adjusting size in em
                  let currEm = parseInt(glyph.style.fontSize);
                  let newEm = currEm * 256 / glyph.offsetHeight;
                  console.log(`currEm=${currEm}`);
                  console.log(`newEm=${newEm}`);
                  glyph.style.fontSize = `${newEm}em`;

                  // also center in resolution on x
                  xOffset = -(glyph.offsetWidth - RESOLUTION) / 2;
                  glyph.style.marginLeft = `${xOffset}px`

                }
            </script>
        """.replace(
                    "FONT_LOCATION", font_file
                )
                .replace("RESOLUTION", str(FLAGS.resolution))
                .replace("ACTIVATION", activation)
            )
        )


if __name__ == "__main__":
    app.run(main)
