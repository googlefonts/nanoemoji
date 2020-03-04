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
from color_glyph import ColorGlyph
from fontTools import ttLib
from fontTools.pens.transformPen import TransformPen
import io
from itertools import chain
from nanosvg.svg import SVG
from nanosvg.svg_pathops import skia_path
import os
import regex
import sys
import ufoLib2
import ufo2ft


# A color font generator.
#   apply_ufo(ufo, color_glyphs) is called first, to update a generated UFO
#   apply_ttfont(ufo, color_glyphs, ttfont) is called second, to allow fixups after ufo2ft
# Ideally we delete the ttfont stp in future. Blocking issues:
#   https://github.com/unified-font-object/ufo-spec/issues/104
# If the output file is .ufo then apply_ttfont is not called.
# Where possible code to the ufo and let apply_ttfont be a nop.
ColorGenerator = collections.namedtuple('ColorGenerator', ['apply_ufo', 'apply_ttfont'])

_COLOR_FORMAT_GENERATORS = {
    'colr_0': ColorGenerator(lambda *args: _colr_v0_ufo(*args),
                             lambda *_: None),
    'colr_1': ColorGenerator(lambda *args: _not_impl('ufo', *args),
                             lambda *args: _not_impl('TTFont', *args)),
    'svg': ColorGenerator(lambda *_: None,
                          lambda *args: _svg_ttfont(*args, zip=False)),
    'svgz': ColorGenerator(lambda *_: None,
                           lambda *args: _svg_ttfont(*args, zip=True)),
    'cbdt': ColorGenerator(lambda *args: _not_impl('ufo', *args),
                           lambda *args: _not_impl('TTFont', *args)),
    'sbix': ColorGenerator(lambda *args: _not_impl('ufo', *args),
                           lambda *args: _not_impl('TTFont', *args)),
}

FLAGS = flags.FLAGS

# TODO move to config file?
flags.DEFINE_integer('upem', 1024, 'Units per em.')
flags.DEFINE_string('family', 'An Emoji Family', 'Family name.')
flags.DEFINE_enum('color_format', 'colr_0',
                  sorted(_COLOR_FORMAT_GENERATORS.keys()),
                  'Type of color font to generate.')
flags.DEFINE_string('output_file', '/tmp/AnEmojiFamily-Regular.ttf',
                    'Dest file, can be .ttf, .otf, or .ufo')


def _codepoints_from_filename(filename):
    match = regex.search(r'(?:[-_]?([0-9a-fA-F]{4,}))+', filename)
    if match:
        return tuple(int(s, 16) for s in match.captures(1))
    logging.warning(f'Bad filename {filename}; unable to extract codepoints')
    return None


def _nanosvg(filename):
    try:
        return SVG.parse(filename).tonanosvg()
    except Exception as e:
        logging.warning(f'{filename} failed: {e}')
    return None


def _inputs(filenames):
    for filename in filenames:
        codepoints = _codepoints_from_filename(filename)
        nanosvg = _nanosvg(filename)
        if codepoints and nanosvg:
            yield (filename, codepoints, nanosvg)


def _ufo(family, upem):
    ufo = ufoLib2.Font()
    ufo.info.familyName = family
    # set various font metadata; see the full list of fontinfo attributes at
    # http://unifiedfontobject.org/versions/ufo3/fontinfo.plist/
    ufo.info.unitsPerEm = upem

    # Must have .notdef and Win 10 Chrome likes a blank gid1 so make that space
    ufo.newGlyph('.notdef')
    space = ufo.newGlyph('.space')
    space.unicodes = [0x0020]
    space.width = upem
    ufo.glyphOrder = ['.notdef', '.space']

    return ufo


def _layer(ufo, idx):
    """UFO has a global set of layers.

    Each layer then has glyphs. For an N-layer COLR glyph we
    write the glyph into global layers 0..N-1. The UFO will end up with
    as many global layers as the "deepest" glyph.

    The only real significance is z-order so name on that basis.
    """
    name = f'z_{idx}'
    if name not in ufo.layers:
        ufo.newLayer(name)
    return ufo.layers[name]


def _make_ttfont(format, ufo, color_glyphs):
    if format == '.ufo':
        return None

    # Use skia-pathops to remove overlaps (i.e. simplify self-overlapping
    # paths) because the default ("booleanOperations") does not support
    # quadratic bezier curves (qcurve), which may appear
    # when we pass through nanosvg (e.g. arcs or stroked paths).
    ttfont = None
    if format == ".ttf":
        ttfont = ufo2ft.compileTTF(ufo, overlapsBackend="pathops")
    if format == ".otf":
        ttfont = ufo2ft.compileOTF(ufo, overlapsBackend="pathops")
    
    if not ttfont:
        raise ValueError('Unable to generate ' + output_file)

    # Permit fixups where we can't express something adequately in UFO
    _COLOR_FORMAT_GENERATORS[FLAGS.color_format].apply_ttfont(ufo, color_glyphs, ttfont)

    return ttfont


def _write(ufo, ttfont, output_file):
    logging.info('Writing %s', output_file)

    if os.path.splitext(output_file)[1] == ".ufo":
        ufo.save(output_file, overwrite=True)
    else:
        ttfont.save(output_file)


def _not_impl(*_):
    raise NotImplementedError('%s not implemented' % FLAGS.color_format)


def _colr_v0_ufo(ufo, color_glyphs):
    # Sort colors so the index into colors == index into CPAL palette
    colors = sorted(set(chain.from_iterable((g.colors() for g in color_glyphs))))
    logging.debug('colors %s', colors)

    # KISS; use a single global palette
    ufo.lib[ufo2ft.constants.COLOR_PALETTES_KEY] = [[c.to_ufo_color() for c in colors]]

    # We created glyph_name on the default layer for the base glyph
    # Now create glyph_name on layers 0..N-1 for the colored layers
    for color_glyph in color_glyphs:
        layer_to_palette_idx = []
        svg_units_to_font_units = color_glyph.transform_for_font_space()
        for idx, (color, path) in enumerate(color_glyph.as_colored_layers()):
            glyph_layer = _layer(ufo, idx)

            # path needs to be draw in specified color on glyph_layer
            palette_idx = colors.index(color)
            layer_to_palette_idx.append((glyph_layer.name, palette_idx))

            # we've got a colored layer, put a glyph on it
            glyph = glyph_layer.newGlyph(color_glyph.glyph_name)
            glyph.width = ufo.info.unitsPerEm

            pen = TransformPen(glyph.getPen(), svg_units_to_font_units)
            skia_path(path).draw(pen)


        # each base glyph contains a list of (layer.name, color_palette_id) in z-order
        base_glyph = ufo.get(color_glyph.glyph_name)
        base_glyph.lib[ufo2ft.constants.COLOR_LAYER_MAPPING_KEY] = layer_to_palette_idx

    # Magic Incantation.
    # the filter below is required to enable the copying of the color layers
    # to standalone glyphs in the default glyph set used to build the TTFont
    # TODO(anthrotype) Make this automatic somehow?
    ufo.lib[ufo2ft.constants.FILTERS_KEY] = [
        {"name": "Explode Color Layer Glyphs", "pre": True}
    ]


def _svg_ttfont(ufo, color_glyphs, ttfont, zip=False):
    svg_table = ttLib.newTable('SVG ')
    svg_table.compressed = zip
    svg_table.docList = [(c.nsvg
                          # dumb sizing isn't useful
                          .remove_attributes(('width', 'height'))
                          # Firefox likes to render blank if present
                          .remove_attributes(('enable-background',))
                          # Required to match gid
                          .set_attributes((('id', f'glyph{c.glyph_id}'),))
                          .tostring(),
                          ttfont.getGlyphID(c.glyph_name), 
                          ttfont.getGlyphID(c.glyph_name))
                         for c in color_glyphs]
    ttfont[svg_table.tableTag] = svg_table


def main(argv):
    inputs = list(_inputs(argv[1:]))
    logging.info(f'{len(inputs)}/{len(argv[1:])} inputs prepared successfully')

    ufo = _ufo(FLAGS.family, FLAGS.upem)
    base_gid = len(ufo.glyphOrder)
    color_glyphs = [ColorGlyph.create(ufo, filename, base_gid + idx, codepoints, nsvg)
                    for idx, (filename, codepoints, nsvg) in enumerate(inputs)]
    ufo.glyphOrder = ufo.glyphOrder + [g.glyph_name for g in color_glyphs]
    for g in color_glyphs:
        assert g.glyph_id == ufo.glyphOrder.index(g.glyph_name)

    _COLOR_FORMAT_GENERATORS[FLAGS.color_format].apply_ufo(ufo, color_glyphs)

    format = os.path.splitext(FLAGS.output_file)[1]
    ttfont = _make_ttfont(format, ufo, color_glyphs)

    # TODO may wish to nuke 'post' glyph names

    _write(ufo, ttfont, FLAGS.output_file)
    logging.info('Wrote %s' % FLAGS.output_file)


if __name__ == "__main__":
    app.run(main)
