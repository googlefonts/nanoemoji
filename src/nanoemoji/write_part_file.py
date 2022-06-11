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

"""Generates a part file from 1 source, typically an svg file.
"""


from absl import app
from absl import flags
from nanoemoji.parts import ReusableParts
from nanoemoji import util
from pathlib import Path
from picosvg.geometric_types import Rect
from picosvg.svg import SVG


FLAGS = flags.FLAGS


flags.DEFINE_integer("wh", None, "The width and height to use.")
flags.DEFINE_bool("compute_donors", False, "Whether to compute donors.")


def main(argv):
    if len(argv) != 2:
        raise ValueError("Specify exactly one input")

    view_box = Rect(0, 0, FLAGS.wh, FLAGS.wh)
    parts = ReusableParts(view_box=view_box, reuse_tolerance=FLAGS.reuse_tolerance)

    svg = SVG.parse(Path(argv[1]))
    parts.add(svg)

    if FLAGS.compute_donors:
        parts.compute_donors()

    with util.file_printer(FLAGS.output_file) as print:
        print(parts.to_json())


if __name__ == "__main__":
    flags.mark_flag_as_required("wh")
    flags.mark_flag_as_required("reuse_tolerance")
    app.run(main)
