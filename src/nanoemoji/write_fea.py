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

"""Writes a fea file for ligature lookup for multi-codepoint RGIs"""

# TODO if this is a qualified sequence create the unqualified version and vice versa


from typing import Sequence
from absl import app
from absl import flags
from nanoemoji import glyphmap
from nanoemoji import features
from nanoemoji import util

FLAGS = flags.FLAGS

flags.DEFINE_string("output_file", "-", "Output filename ('-' means stdout)")


def main(argv: Sequence[str]) -> None:
    with util.file_printer(FLAGS.output_file) as print:
        sequences = sorted(
            {
                gm.codepoints
                for gm in glyphmap.parse_csv(argv[1])
                if len(gm.codepoints) > 1
            }
        )
        print(features.generate_fea(sequences))


if __name__ == "__main__":
    app.run(main)
