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

"""Creates svg files from a COLR table."""
from absl import app
from absl import flags
from absl import logging
from fontTools import ttLib
from nanoemoji.colr_to_svg import colr_to_svg, glyph_region, map_font_space_to_viewbox
from nanoemoji import util
from pathlib import Path
from picosvg.geometric_types import Rect


FLAGS = flags.FLAGS


flags.DEFINE_string("output_dir", None, "Output dir. Files written to <glyph id>.svg.")
flags.DEFINE_string(
    "log_level",
    "INFO",
    "The threshold for what messages will be logged. One of DEBUG, INFO, WARN, "
    "ERROR, or FATAL.",
)


def _view_box(font: ttLib.TTFont, glyph_name: str) -> Rect:
    # we want a viewbox that results in no scaling when translating from font-space
    region = glyph_region(font, glyph_name)
    assert region.w > 0, f"0-width region for {glyph_name}"
    return region


def main(argv):
    logging.set_verbosity(FLAGS.log_level)

    font_file = util.only(argv, lambda a: a.endswith(".ttf"))
    out_dir = Path(FLAGS.output_dir)
    assert out_dir.is_dir(), f"{FLAGS.output_dir} is not a directory"

    font = ttLib.TTFont(font_file)
    assert "COLR" in font, f"No COLR table in {font_file}"
    logging.debug("Writing svgs from %s to %s", font_file, out_dir)

    for glyph_name, svg in colr_to_svg(lambda gn: _view_box(font, gn), font).items():
        gid = font.getGlyphID(glyph_name)
        dest_file = out_dir / f"{gid:05d}.svg"
        with open(dest_file, "w") as f:
            f.write(svg.tostring(pretty_print=True))


if __name__ == "__main__":
    flags.mark_flag_as_required("output_dir")
    app.run(main)
