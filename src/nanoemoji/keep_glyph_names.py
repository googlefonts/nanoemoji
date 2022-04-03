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

"""Update post to keep glyph names."""
from absl import app
from absl import flags
from absl import logging
from fontTools import ttLib
from pathlib import Path


FLAGS = flags.FLAGS


flags.DEFINE_string(
    "log_level",
    "INFO",
    "The threshold for what messages will be logged. One of DEBUG, INFO, WARN, "
    "ERROR, or FATAL.",
)


def keep_glyph_names(font: ttLib.TTFont):
    # ref https://github.com/googlefonts/ufo2ft/blob/ad28eea062e0dd48678309bd9ef86dfcc85fa85a/Lib/ufo2ft/postProcessor.py#L281-L285
    if "post" not in font:
        raise ValueError(f"No post table")
    post = font["post"]
    post.formatType = 2.0
    post.extraNames = []
    post.mapping = {}


def main(argv):
    logging.set_verbosity(FLAGS.log_level)

    assert len(argv) == 3, "Expected 2 args, input font and output font"

    input_file = Path(argv[1])
    assert input_file.is_file(), f"No file {input_file}"
    output_file = Path(argv[2])
    assert input_file.resolve() != output_file.resolve()

    font = ttLib.TTFont(input_file)
    keep_glyph_names(font)

    font.save(output_file)


if __name__ == "__main__":
    app.run(main)
