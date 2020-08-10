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

"""Diff two pngs and save the result.

See:
    https://pillow.readthedocs.io/en/stable/reference/ImageChops.html
    https://pillow.readthedocs.io/en/stable/reference/ImageStat.html
"""
from absl import app
from absl import flags
from absl import logging
from PIL import Image, ImageChops, ImageStat
import os


FLAGS = flags.FLAGS


flags.DEFINE_string("output_file", None, "File contining the diff.")


def _diff_pixel(p):
    if p != (0, 0, 0, 0):
        return (255, 0, 233, 255)
    return p


def _pink_diff_file():
    base, ext = os.path.splitext(FLAGS.output_file)
    return f"{base}.pink{ext}"


def main(argv):
    lhs_file, rhs_file = argv[1:]
    lhs, rhs = Image.open(lhs_file), Image.open(rhs_file)
    diff = ImageChops.difference(lhs, rhs)

    diff.save(FLAGS.output_file)

    # The default diff is really hard; make it more obvoius
    diff.putdata([_diff_pixel(p) for p in diff.getdata()])

    diff.save(_pink_diff_file())


if __name__ == "__main__":
    app.run(main)
