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

"""Helps deal with emoji codepoints."""

import os
import regex
import absl


def from_filename(filename):
    match = regex.search(r"(?:^emoji_u)?(?:[-_]?([0-9a-fA-F]{1,}))+", filename)
    if not match:
        raise ValueError(f"Bad filename {filename}; unable to extract codepoints")
    return tuple(int(s, 16) for s in match.captures(1))


def csv_line(filename):
    filename = os.path.basename(filename)
    codepoints = ",".join("%04x" % c for c in from_filename(filename))
    return f"{filename},{codepoints}"


def parse_csv_line(line):
    parts = line.split(",")
    return (parts[0], tuple(int(p, 16) for p in parts[1:]))


def parse_csv(filename):
    with open(filename) as f:
        return [parse_csv_line(l) for l in f]
