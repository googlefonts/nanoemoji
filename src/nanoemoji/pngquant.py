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
"""Wrapper around pngquant command.

This runs the pnquant command as a subprocess, forwarding all the unparsed options
after '--', while also handling two special error codes 98 or 99 by simply copying the
input file to the output file.
Pngquant exits with 98 when the conversion results in a larger file than the original;
and with 99 when the conversion results in quality below the requested minimum.

Usage:

    $ python -m nanoemoji.pngquant -i INPUT -o OUTPUT -- [PNGQUANTFLAGS]
"""

from absl import app
from absl import flags
import shlex
import shutil
import subprocess


FLAGS = flags.FLAGS

flags.DEFINE_string("input_file", None, "Input filename", short_name="i")
flags.DEFINE_string("output_file", None, "Output filename", short_name="o")


def main(argv):
    pngquant = shutil.which("pngquant")
    if pngquant is None:
        raise RuntimeError(
            "'pngquant' command-line tool not found on $PATH. "
            "Try `pip install pngquant-cli` or visit https://github.com/kornelski/pngquant."
        )
    pngquant_args = argv[1:]
    infile = FLAGS.input_file
    outfile = FLAGS.output_file
    p = subprocess.run([pngquant, *pngquant_args, "-o", outfile, infile])
    err = p.returncode
    if err in (98, 99):
        print(f"Reuse {infile}")
        shutil.copyfile(infile, outfile)
        err = 0
    return err


if __name__ == "__main__":
    flags.mark_flag_as_required("input_file")
    flags.mark_flag_as_required("output_file")
    app.run(main)
