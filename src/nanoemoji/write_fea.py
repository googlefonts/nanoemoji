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


from absl import app
from nanoemoji import codepoints
from nanoemoji.glyph import glyph_name


def _generate_fea(rgi_sequences):
    rules = []
    rules.append("languagesystem DFLT dflt;")
    rules.append("languagesystem latn dflt;")
    rules.append("")

    rules.append("feature rlig {")
    for rgi in sorted(rgi_sequences):
        if len(rgi) == 1:
            continue
        glyphs = [glyph_name(cp) for cp in rgi]
        target = glyph_name(rgi)
        rules.append("  sub %s by %s;" % (" ".join(glyphs), target))

    rules.append("} rlig;")
    rules.append("")
    return "\n".join(rules)


def main(argv):
    with open(argv[1]) as f:
        rgi_sequences = sorted(codepoints.parse_csv_line(l)[1] for l in f)
    print(_generate_fea(rgi_sequences))


if __name__ == "__main__":
    app.run(main)
