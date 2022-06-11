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

"""Combines N part files to 1"""


from absl import app
from absl import flags
from nanoemoji.parts import ReusableParts
from nanoemoji import util
from pathlib import Path


FLAGS = flags.FLAGS


def main(argv):
    input_files = util.expand_ninja_response_files(argv[1:])

    combined_parts = ReusableParts()
    individual_parts = [ReusableParts.loadjson(Path(p)) for p in input_files]
    if individual_parts:
        combined_parts.version = util.only({p.version for p in individual_parts})
        combined_parts.reuse_tolerance = util.only(
            {p.reuse_tolerance for p in individual_parts}
        )
        combined_parts.view_box = util.only({p.view_box for p in individual_parts})

    for parts in individual_parts:
        combined_parts.add(parts)

    combined_parts.compute_donors()  # precompute for later use

    with util.file_printer(FLAGS.output_file) as print:
        print(combined_parts.to_json())


if __name__ == "__main__":
    app.run(main)
