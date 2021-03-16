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

"""Prints a csv of filename,codepoint sequence"""

from absl import app
from absl import flags
from nanoemoji import codepoints
from nanoemoji import util


FLAGS = flags.FLAGS

flags.DEFINE_string("output_file", "-", "Output filename ('-' means stdout)")


def main(argv):
    with util.file_printer(FLAGS.output_file) as print:
        for filename in util.expand_ninja_response_files(argv[1:]):
            if filename.endswith(".txt"):
                with open(filename) as f:
                    for l in f:
                        print(codepoints.csv_line(l.strip()))
            else:
                print(codepoints.csv_line(filename))


if __name__ == "__main__":
    app.run(main)
