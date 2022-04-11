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

from absl import app
from pathlib import Path
import shutil


def main(argv):
    assert len(argv) == 3, "Expected 2 args, input font and output"

    input_file = Path(argv[1])
    assert input_file.is_file(), f"No file {input_file}"
    output_file = Path(argv[2])
    assert input_file.resolve() != output_file.resolve()

    shutil.copyfile(input_file, output_file)


if __name__ == "__main__":
    app.run(main)
