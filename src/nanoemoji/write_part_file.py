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

"""Generates a part file from 1..N input part sources.

Part sources can be:

1. Other part files
2. Svg files

Or any mix thereof.
"""


from absl import app
from absl import flags
from functools import reduce
from nanoemoji.parts import ReuseableParts
from nanoemoji import util
from pathlib import Path


FLAGS = flags.FLAGS


def main(argv):
    parts = [ReuseableParts.load(Path(part_file)) for part_file in argv[1:]]
    if not parts:
        raise ValueError("Specify at least one input")
    parts = reduce(lambda a, c: a.add(c), parts[1:], parts[0])

    with util.file_printer(FLAGS.output_file) as print:
        print(parts.to_json())


if __name__ == "__main__":
    app.run(main)
