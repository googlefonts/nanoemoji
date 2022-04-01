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
from fontTools import ttLib
from nanoemoji import config
from nanoemoji import util
from pathlib import Path
import textwrap


FLAGS = flags.FLAGS


def main(argv):
    font_file = util.only(argv, lambda a: a.endswith(".ttf"))
    config_file = Path(util.only(argv, lambda a: a.endswith(".toml")))
    font = ttLib.TTFont(font_file)
    upem = font["head"].unitsPerEm
    ascender = font["OS/2"].sTypoAscender
    descender = font["OS/2"].sTypoDescender

    with open(config_file, "w") as f:
        f.write(
            textwrap.dedent(
                f"""
            output_file = "COLR.ttf"
            color_format = "{FLAGS.color_format}"
            upem = {upem}
            width = 0  # from input width
            ascender = {ascender}
            descender = {descender}
            keep_glyph_names = true

            fea_file = ""

            [axis.wght]
            name = "Weight"
            default = 400

            [master.regular]
            style_name = "Regular"

            [master.regular.position]
            wght = 400
            """
            )
        )


if __name__ == "__main__":
    app.run(main)
