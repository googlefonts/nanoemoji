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

"""Update post to drop glyph names."""
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


def main(argv):
    logging.set_verbosity(FLAGS.log_level)

    assert len(argv) == 3, "Expected 2 args, input font and output font"

    input_file = Path(argv[1])
    assert input_file.is_file(), f"No file {input_file}"
    output_file = Path(argv[2])
    assert input_file.resolve() != output_file.resolve()

    font = ttLib.TTFont(input_file)

    post = font["post"]
    post.formatType = 3.0
    for attr in ("extraNames", "mapping"):
        if hasattr(post, attr):
            delattr(post, attr)
    post.glyphOrder = None

    font.save(output_file)


if __name__ == "__main__":
    app.run(main)
