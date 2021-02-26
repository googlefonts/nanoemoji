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

"""Assembles UFOs into a variable font.

Based on https://gist.github.com/anthrotype/c11515065a4aa6549f9d5f2dfdcf8f23"""

from absl import app
from absl import logging
from fontTools import designspaceLib
from nanoemoji import config
import ufo2ft
import ufoLib2


def main(argv):
    ufos = tuple(a for a in argv[1:] if a.endswith(".ufo"))

    font_config = config.load()

    designspace = designspaceLib.DesignSpaceDocument()

    import pprint

    pp = pprint.PrettyPrinter()

    # define axes names, tags and min/default/max
    axis_defs = [
        dict(
            tag=a.axisTag,
            name=a.name,
            minimum=min(
                p.position
                for m in font_config.masters
                for p in m.position
                if p.axisTag == a.axisTag
            ),
            default=a.default,
            maximum=max(
                p.position
                for m in font_config.masters
                for p in m.position
                if p.axisTag == a.axisTag
            ),
        )
        for a in font_config.axes
    ]
    logging.info(pp.pformat(axis_defs))
    for axis_def in axis_defs:
        designspace.addAxisDescriptor(**axis_def)

    axis_names = {a.axisTag: a.name for a in font_config.axes}
    for master in font_config.masters:
        ufo = ufoLib2.Font.open(master.output_ufo)
        ufo.info.styleName = master.style_name
        location = {axis_names[p.axisTag]: p.position for p in master.position}
        designspace.addSourceDescriptor(
            name=master.output_ufo, location=location, font=ufo
        )

    # build a variable TTFont from the designspace document
    # TODO: Use ufo2ft.compileVariableCFF2 for CFF
    vf = ufo2ft.compileVariableTTF(designspace)
    vf.save(font_config.output_file)


if __name__ == "__main__":
    app.run(main)
