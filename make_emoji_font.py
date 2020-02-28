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
from colors import Color
from fontTools.misc.transform import Transform
from nanosvg.svg import SVG
import os
import regex
import sys

import ufoLib2
import ufo2ft

FLAGS = flags.FLAGS

# TODO move to config file?
flags.DEFINE_integer('upem', 1024, 'Units per em.')
flags.DEFINE_string('family', 'An Emoji Family', 'Family name.')
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


def _transform(filename, upem, nsvg):
    vbox = nsvg.view_box()
    if vbox is None:
        logging.warning(f'{filename} has no vbox; no transform will be applied')
        return Transform()
    if vbox[0:2] != (0, 0):
        raise ValueError('viewBox must start at 0,0')
    x_scale = upem / vbox[2]
    y_scale = upem / vbox[3]
    transform = Transform(x_scale, 0, 0, -y_scale, 0, upem)
    logging.debug('%s %s', os.path.basename(filename), transform)
    return transform


def _inputs(filenames):
    for filename in filenames:
        codepoints = _codepoints_from_filename(filename)
        nanosvg = _nanosvg(filename)
        if codepoints and nanosvg:
            yield (filename, codepoints, nanosvg)


def _glyph_name(codepoints):
    return 'emoji_' + '_'.join(('%04x' % c for c in sorted(codepoints)))


def _colored_glyphs(nsvg):
    """Yields (Color, SVGPath) tuples to draw nsvg."""
    for shape in nsvg.shapes():
        if regex.match(r'^url[(]#[^)]+[)]$', shape.fill):
            logging.warning('TODO process fill=%s (probably gradient)', shape.fill)
            shape.fill = 'black'
        paint = Color.fromstring(shape.fill, alpha=shape.opacity)
        yield (paint, shape)


def _ufo(family, upem):
    ufo = ufoLib2.Font()
    ufo.info.familyName = family
    # set various font metadata; see the full list of fontinfo attributes at
    # http://unifiedfontobject.org/versions/ufo3/fontinfo.plist/
    ufo.info.unitsPerEm = upem
    return ufo


def _layer(ufo, name):
    if name not in ufo.layers:
        ufo.newLayer(name)
    return ufo.layers[name]


def _write(ufo, output_file):
    # Magic Incantation.
    # the filter below is required to enable the copying of the color layers
    # to standalone glyphs in the default glyph set used to build the TTFont
    # TODO(anthrotype) Make this automatic somehow?
    ufo.lib[ufo2ft.constants.FILTERS_KEY] = [
        {"name": "Explode Color Layer Glyphs", "pre": True}
    ]

    format = os.path.splitext(output_file)[1]

    if format == ".ufo":
        ufo.save(output_file, overwrite=True)
        return

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

    logging.info('Writing %s', output_file)
    ttfont.save(output_file)



def main(argv):
    inputs = list(_inputs(argv[1:]))
    logging.info(f'{len(inputs)}/{len(argv[1:])} inputs prepared successfully')

    ufo = _ufo(FLAGS.family, FLAGS.upem)

    ufo_colors = set()

    for filename, codepoints, nsvg in inputs:
        glyph_name = _glyph_name(codepoints)
        logging.info('Begin %s', glyph_name)

        colored_glyphs = _colored_glyphs(nsvg)
        ufo_colors.update((c.to_ufo_color() for c, _ in colored_glyphs))

        base_glyph = ufo.newGlyph(glyph_name)

        # If we can directly cmap tell UFO about it
        if len(codepoints) == 1:
            base_glyph.unicode = next(iter(codepoints))
        else:
            # Multi-codepoint seq; need an rlig
            logging.warning('TODO prepare for rlig => glyph')

    print(sorted(ufo_colors))

    # KISS; use a single global palette
    ufo.lib[ufo2ft.constants.COLOR_PALETTES_KEY] = [sorted(ufo_colors)]

    _write(ufo, FLAGS.output_file)



if __name__ == "__main__":
    app.run(main)