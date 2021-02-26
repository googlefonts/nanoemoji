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

"""Generate a png using Skia."""
from absl import app
from absl import flags
from absl import logging
from nanoemoji import codepoints
from nanoemoji import util
import os
import shutil
import subprocess
import sys


FLAGS = flags.FLAGS


flags.DEFINE_integer("height", None, "png height, pixels.")
flags.DEFINE_integer("width", None, "png width, pixels.")
flags.DEFINE_string("output_file", None, "Output filename.")


def main(argv):
    src_svg = util.only(lambda a: a.endswith(".svg"), argv)
    font_file = util.only(lambda a: a.endswith(".ttf"), argv)
    text = "".join(
        chr(cp) for cp in codepoints.from_filename(os.path.basename(src_svg))
    )
    logging.info("%s %s", src_svg, text)

    colr_test_cmd = [
        "colr_test",
        "--font",
        font_file,
        "--output",
        FLAGS.output_file,
        "--text",
        text,
    ]
    if FLAGS.height is not None:
        colr_test_cmd.extend(("--height", str(FLAGS.height)))
    if FLAGS.width is not None:
        colr_test_cmd.extend(("--width", str(FLAGS.width)))

    if not shutil.which(colr_test_cmd[0]):
        sys.exit(
            f"{colr_test_cmd[0]} binary (https://github.com/rsheeter/skia_colr/tree/colr_test) must be on PATH"
        )
    logging.info(" ".join(colr_test_cmd))
    subprocess.run(colr_test_cmd, check=True)
    logging.info("Wrote %s", FLAGS.output_file)


if __name__ == "__main__":
    app.run(main)
