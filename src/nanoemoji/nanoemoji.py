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

"""Create an emoji font from a set of SVGs.

UFO handling informed by Cosimo's
https://gist.github.com/anthrotype/2acbc67c75d6fa5833789ec01366a517

For COLR:
    Each SVG file represent one base glyph in the COLR font.
    For each glyph, we get the list of layers associated with it.
    For each layer we have a tuple (Paint, SVGPath).
    To convert to font format we  use the UFO Glyph pen.

Sample usage:
make_emoji_font.py -v 1 $(find ~/oss/noto-emoji/svg -name '*.svg')
make_emoji_font.py $(find ~/oss/twemoji/assets/svg -name '*.svg')
"""
from absl import app
from absl import flags
from absl import logging
import collections
from fontTools import ttLib
from fontTools.pens.transformPen import TransformPen
import io
from itertools import chain
from nanoemoji.color_glyph import ColorGlyph
from nanoemoji.glyph import glyph_name
from picosvg.svg import SVG
from picosvg.svg_pathops import skia_path
import os
import regex
import sys
import ufoLib2
import ufo2ft


ColorFontConfig = collections.namedtuple(
    "ColorFontConfig", ["upem", "family", "color_format", "output_format"]
)

# A color font generator.
#   apply_ufo(ufo, color_glyphs) is called first, to update a generated UFO
#   apply_ttfont(ufo, color_glyphs, ttfont) is called second, to allow fixups after ufo2ft
# Ideally we delete the ttfont stp in future. Blocking issues:
#   https://github.com/unified-font-object/ufo-spec/issues/104
# If the output file is .ufo then apply_ttfont is not called.
# Where possible code to the ufo and let apply_ttfont be a nop.
ColorGenerator = collections.namedtuple("ColorGenerator", ["apply_ufo", "apply_ttfont"])


_COLOR_FORMAT_GENERATORS = {
    "colr_0": ColorGenerator(lambda *args: _colr_ufo(0, *args), lambda *_: None),
    "colr_1": ColorGenerator(lambda *args: _colr_ufo(1, *args), lambda *_: None),
    "svg": ColorGenerator(lambda *_: None, lambda *args: _svg_ttfont(*args, zip=False)),
    "svgz": ColorGenerator(lambda *_: None, lambda *args: _svg_ttfont(*args, zip=True)),
    "cbdt": ColorGenerator(
        lambda *args: _not_impl("ufo", *args), lambda *args: _not_impl("TTFont", *args)
    ),
    "sbix": ColorGenerator(
        lambda *args: _not_impl("ufo", *args), lambda *args: _not_impl("TTFont", *args)
    ),
}


FLAGS = flags.FLAGS


# TODO move to config file?
flags.DEFINE_integer("upem", 1024, "Units per em.")
flags.DEFINE_string("family", "An Emoji Family", "Family name.")
flags.DEFINE_enum(
    "color_format",
    "colr_0",
    sorted(_COLOR_FORMAT_GENERATORS.keys()),
    "Type of color font to generate.",
)
flags.DEFINE_string(
    "output_file",
    "/tmp/AnEmojiFamily-Regular.ttf",
    "Dest file, can be .ttf, .otf, or .ufo",
)


def _codepoints_from_filename(filename):
    match = regex.search(r"(?:^emoji_u)?(?:[-_]?([0-9a-fA-F]{1,}))+", filename)
    if match:
        return tuple(int(s, 16) for s in match.captures(1))
    logging.warning(f"Bad filename {filename}; unable to extract codepoints")
    return None


def _picosvg(filename):
    try:
        return SVG.parse(filename).topicosvg()
    except Exception as e:
        logging.warning(f"{filename} failed: {e}")
    return None


def _inputs(filenames):
    for filename in filenames:
        codepoints = _codepoints_from_filename(os.path.basename(filename))
        picosvg = _picosvg(filename)
        if codepoints and picosvg:
            yield (filename, codepoints, picosvg)


def _ufo(family, upem):
    ufo = ufoLib2.Font()
    ufo.info.familyName = family
    # set various font metadata; see the full list of fontinfo attributes at
    # http://unifiedfontobject.org/versions/ufo3/fontinfo.plist/
    ufo.info.unitsPerEm = upem

    # Must have .notdef and Win 10 Chrome likes a blank gid1 so make gid1 space
    ufo.newGlyph(".notdef")
    space = ufo.newGlyph(".space")
    space.unicodes = [0x0020]
    space.width = upem
    ufo.glyphOrder = [".notdef", ".space"]

    return ufo


def _layer(ufo, idx):
    """UFO has a global set of layers.

    Each layer then has glyphs. For an N-layer COLR glyph we
    write the glyph into global layers 0..N-1. The UFO will end up with
    as many global layers as the "deepest" glyph.

    The only real significance is z-order so name on that basis.
    """
    name = f"z_{idx}"
    if name not in ufo.layers:
        ufo.newLayer(name)
    return ufo.layers[name]


def _make_ttfont(config, ufo, color_glyphs):
    if config.output_format == ".ufo":
        return None

    # Use skia-pathops to remove overlaps (i.e. simplify self-overlapping
    # paths) because the default ("booleanOperations") does not support
    # quadratic bezier curves (qcurve), which may appear
    # when we pass through picosvg (e.g. arcs or stroked paths).
    ttfont = None
    if config.output_format == ".ttf":
        ttfont = ufo2ft.compileTTF(ufo, overlapsBackend="pathops")
    if config.output_format == ".otf":
        ttfont = ufo2ft.compileOTF(ufo, overlapsBackend="pathops")

    if not ttfont:
        raise ValueError(f"Unable to generate {color_format} {dest_format}")

    # Permit fixups where we can't express something adequately in UFO
    _COLOR_FORMAT_GENERATORS[config.color_format].apply_ttfont(
        ufo, color_glyphs, ttfont
    )

    return ttfont


def _write(ufo, ttfont, output_file):
    logging.info("Writing %s", output_file)

    if os.path.splitext(output_file)[1] == ".ufo":
        ufo.save(output_file, overwrite=True)
    else:
        ttfont.save(output_file)


def _not_impl(*_):
    raise NotImplementedError("%s not implemented" % FLAGS.color_format)


def _colr_ufo(colr_version, ufo, color_glyphs):
    # Sort colors so the index into colors == index into CPAL palette.
    # We only store opaque colors in CPAL for CORLv1, as 'transparency' is
    # encoded separately.
    colors = sorted(
        set(
            c if colr_version == 0 else c.opaque()
            for c in chain.from_iterable(g.colors() for g in color_glyphs)
        )
    )
    logging.debug("colors %s", colors)

    # KISS; use a single global palette
    ufo.lib[ufo2ft.constants.COLOR_PALETTES_KEY] = [[c.to_ufo_color() for c in colors]]

    # We created glyph_name on the default layer for the base glyph
    # Now create glyph_name on layers 0..N-1 for the colored layers
    for color_glyph in color_glyphs:
        # For COLRv0, paint is just the palette index
        # For COLRv1, it's a data structure describing paint
        layer_to_paint = []
        svg_units_to_font_units = color_glyph.transform_for_font_space()
        logging.debug(
            "%s %s %s",
            ufo.info.familyName,
            color_glyph.glyph_name,
            svg_units_to_font_units,
        )
        for idx, (paint, path) in enumerate(color_glyph.as_painted_layers()):
            glyph_layer = _layer(ufo, idx)

            if colr_version == 0:
                # COLRv0: draw using the first available color on the glyph_layer
                # Results for gradients will be suboptimal :)
                color = next(paint.colors())
                layer_to_paint.append((glyph_layer.name, colors.index(color)))

            elif colr_version == 1:
                # COLRv0: fill in gradient paint structures
                layer_to_paint.append((glyph_layer.name, paint.to_ufo_paint(colors)))

            else:
                raise ValueError(f"Unsupported COLR version: {colr_version}")

            # we've got a colored layer, put a glyph on it
            glyph = glyph_layer.newGlyph(color_glyph.glyph_name)
            glyph.width = ufo.info.unitsPerEm

            pen = TransformPen(glyph.getPen(), svg_units_to_font_units)
            skia_path(path).draw(pen)

        # each base glyph contains a list of (layer.name, paint info) in z-order
        base_glyph = ufo.get(color_glyph.glyph_name)
        base_glyph.lib[ufo2ft.constants.COLOR_LAYER_MAPPING_KEY] = layer_to_paint

        # apparently on Mac (but not Linux) Chrome and Firefox end up relying on the
        # extents of the base layer to determine where the glyph might paint. If you
        # leave the base blank the COLR glyph never renders.
        pen = base_glyph.getPen()
        pen.moveTo((0, 0))
        pen.lineTo((ufo.info.unitsPerEm, ufo.info.unitsPerEm))
        pen.endPath()


def _svg_ttfont(ufo, color_glyphs, ttfont, zip=False):
    svg_table = ttLib.newTable("SVG ")
    svg_table.compressed = zip
    svg_table.docList = [
        (
            c.nsvg
            # dumb sizing isn't useful
            .remove_attributes(("width", "height"))
            # Firefox likes to render blank if present
            .remove_attributes(("enable-background",))
            # Required to match gid
            .set_attributes((("id", f"glyph{c.glyph_id}"),)).tostring(),
            ttfont.getGlyphID(c.glyph_name),
            ttfont.getGlyphID(c.glyph_name),
        )
        for c in color_glyphs
    ]
    ttfont[svg_table.tableTag] = svg_table


def _generate_fea(rgi_sequences):
    # TODO if this is a qualified sequence create the unqualified version and vice versa
    rules = []
    rules.append("languagesystem DFLT dflt;")
    rules.append("languagesystem latn dflt;")

    rules.append("feature rlig {")
    for rgi, target in sorted(rgi_sequences):
        if len(rgi) == 1:
            continue
        glyphs = [glyph_name(cp) for cp in rgi]
        rules.append("  sub %s by %s;" % (" ".join(glyphs), target))

    rules.append("} rlig;")
    return "\n".join(rules)


def _ensure_codepoints_will_have_glyphs(ufo, glyph_inputs):
    """Ensure all codepoints we use will have a glyph.

    Single codepoint sequences will directly mapped to their glyphs.
    We need to add a glyph for any codepoint that is only used in a multi-codepoint sequence.

    """
    all_codepoints = set()
    direct_mapped_codepoints = set()
    for _, codepoints, _ in glyph_inputs:
        if len(codepoints) == 1:
            direct_mapped_codepoints.update(codepoints)
        all_codepoints.update(codepoints)

    need_blanks = all_codepoints - direct_mapped_codepoints
    logging.debug("%d codepoints require blanks", len(need_blanks))
    glyph_names = []
    for codepoint in need_blanks:
        # Any layer is fine; we aren't going to draw
        glyph = ufo.newGlyph(glyph_name(codepoint))
        glyph.unicode = codepoint
        glyph_names.append(glyph.name)

    ufo.glyphOrder = ufo.glyphOrder + sorted(glyph_names)


def _generate_color_font(config, glyph_inputs):
    """Make a UFO and optionally a TTFont from svgs.

    Args:
        color_font_config: ColorFontConfig
        glyph_inputs: sequence of (filename, codepoints, picosvg) tuples
    """
    ufo = _ufo(config.family, config.upem)
    _ensure_codepoints_will_have_glyphs(ufo, glyph_inputs)

    base_gid = len(ufo.glyphOrder)
    color_glyphs = [
        ColorGlyph.create(ufo, filename, base_gid + idx, codepoints, nsvg)
        for idx, (filename, codepoints, nsvg) in enumerate(glyph_inputs)
    ]
    ufo.glyphOrder = ufo.glyphOrder + [g.glyph_name for g in color_glyphs]
    for g in color_glyphs:
        assert g.glyph_id == ufo.glyphOrder.index(g.glyph_name)

    _COLOR_FORMAT_GENERATORS[config.color_format].apply_ufo(ufo, color_glyphs)

    ufo.features.text = _generate_fea(
        [(c.codepoints, c.glyph_name) for c in color_glyphs]
    )
    logging.debug("fea:\n%s\n" % ufo.features.text)

    ttfont = _make_ttfont(config, ufo, color_glyphs)

    # TODO may wish to nuke 'post' glyph names

    return ufo, ttfont


def _run(argv):
    config = ColorFontConfig(
        upem=FLAGS.upem,
        family=FLAGS.family,
        color_format=FLAGS.color_format,
        output_format=os.path.splitext(FLAGS.output_file)[1],
    )

    inputs = list(_inputs(argv[1:]))
    if not inputs:
        sys.exit("Please provide at least one svg filename")

    logging.info(f"{len(inputs)}/{len(argv[1:])} inputs prepared successfully")

    ufo, ttfont = _generate_color_font(config, inputs)

    _write(ufo, ttfont, FLAGS.output_file)
    logging.info("Wrote %s" % FLAGS.output_file)


def main():
    # We don't seem to be __main__ when run as cli tool installed by setuptools
    app.run(_run)


if __name__ == "__main__":
    app.run(_run)
