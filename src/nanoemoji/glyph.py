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

_MAX_NAME_LEN = 63  # fea for some reason insists on this


# str.isascii was added with python 3.7
try:
    _isascii = str.isascii  # type: ignore
except AttributeError:

    def _isascii(s: str) -> bool:
        try:
            s.encode("ascii")
        except UnicodeEncodeError:
            return False
        else:
            return True


def _name(cp):
    ch = chr(cp)
    if ch.isalpha() and _isascii(ch):
        return ch
    return "%x" % cp


def glyph_name(codepoints):
    try:
        iter(codepoints)
    except TypeError:
        codepoints = [codepoints]
    name = "_".join((_name(c) for c in codepoints))
    if len(name) > _MAX_NAME_LEN:
        import hashlib
        import base64

        hash = hashlib.sha1()  # don't care if secure
        hash.update(name.encode("utf-8"))
        name = base64.b32encode(hash.digest()).decode("utf-8")
    if not name[0].isalpha():
        name = "g_" + name
    return name
