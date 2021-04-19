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

"""Helps deal with emoji OpenType Layout features."""

# TODO if this is a qualified sequence create the unqualified version and vice versa


from nanoemoji.glyph import glyph_name


DEFAULT_GSUB_FEATURE_TAG = "ccmp"


def generate_fea(rgi_sequences, feature_tag=DEFAULT_GSUB_FEATURE_TAG):
    # Generate feature with ligature lookup for multi-codepoint RGIs
    rules = []
    rules.append("languagesystem DFLT dflt;")
    rules.append("languagesystem latn dflt;")
    rules.append("")

    rules.append(f"feature {feature_tag} {{")
    for rgi in sorted(rgi_sequences):
        if len(rgi) == 1:
            continue
        glyphs = [glyph_name(cp) for cp in rgi]
        target = glyph_name(rgi)
        rules.append("  sub %s by %s;" % (" ".join(glyphs), target))

    rules.append(f"}} {feature_tag};")
    rules.append("")
    return "\n".join(rules)
