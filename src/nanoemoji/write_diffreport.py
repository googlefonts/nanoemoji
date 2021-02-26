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

"""Writes a simple html report on a set of image diffs."""
from absl import app
from absl import flags
from absl import logging
import functools
from PIL import Image, ImageChops, ImageStat
from pathlib import Path
from textwrap import dedent
from nanoemoji import util


FLAGS = flags.FLAGS


flags.DEFINE_string("lhs_dir", None, "Directory with lhs images for diffs.")
flags.DEFINE_string("rhs_dir", None, "Directory with rhs images for diffs.")
flags.DEFINE_string("output_file", None, "Output filename.")
flags.DEFINE_integer(
    "report_max_entries", 128, "Show the worst (biggest diff) N emoji."
)


def _diff_value(diff_file):
    return sum(ImageStat.Stat(Image.open(diff_file)).sum2)


def _lhs(diff_file):
    return Path(FLAGS.lhs_dir) / diff_file.name


def _rhs(diff_file):
    return Path(FLAGS.rhs_dir) / diff_file.name


def main(argv):
    diff_files = (
        Path(diff_file) for diff_file in util.expand_ninja_response_files(argv[1:])
    )
    diff_files = sorted(diff_files, key=_diff_value, reverse=True)
    with open(FLAGS.output_file, "w") as f:
        f.write(
            dedent(
                """
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                img {
                    display: inline-block;
                }
                .filename {
                    font-family: monospace;
                }
                .title {
                    font-family: monospace;
                    font-weight: bold;
                    font-size: 2em;
                    width: 256px;
                    display: inline-block;
                }
            </style>
        </head>

        <body>
            <div>
                <span class="title">resvg</span>
                <span class="title">Bad Pixels</span>
                <span class="title">Skia</span>
            </div>
        """
            )
        )
        for diff_file in diff_files[: FLAGS.report_max_entries]:
            logging.info("%s %s", diff_file.name, _diff_value(diff_file))
            pink_diff = diff_file.parent / (diff_file.stem + ".pink" + diff_file.suffix)
            vars = {
                "lhs_file": str(_lhs(diff_file)),
                "rhs_file": str(_rhs(diff_file)),
                "diff_file": str(pink_diff),
                "filename": diff_file.name,
            }
            f.write(
                dedent(
                    """
            <div class="row">
                <div class="filename">{filename}</div>
                <img src="{lhs_file}">
                <img src="{diff_file}">
                <img src="{rhs_file}">
            </div>
            """.format(
                        **vars
                    )
                )
            )

        f.write(
            dedent(
                """
        </body>

        </html>
        """
            )
        )


if __name__ == "__main__":
    app.run(main)
