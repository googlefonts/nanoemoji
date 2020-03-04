from absl import logging
from fontTools.misc.transform import Transform
import collections
from colors import Color
import regex


def _glyph_name(codepoints):
    return 'emoji_' + '_'.join(('%04x' % c for c in codepoints))


def _color(shape):
    if regex.match(r'^url[(]#[^)]+[)]$', shape.fill):
        logging.warning('TODO process fill=%s (probably gradient)', shape.fill)
        shape.fill = 'black'
    return Color.fromstring(shape.fill, alpha=shape.opacity)


class ColorGlyph(collections.namedtuple("ColorGlyph", ['ufo', 'filename', 'glyph_name', 'glyph_id', 'codepoints', 'nsvg'])):
    @staticmethod
    def create(ufo, filename, glyph_id, codepoints, nsvg):
        logging.info(' ColorGlyph for %s', filename)
        glyph_name = _glyph_name(codepoints)
        base_glyph = ufo.newGlyph(glyph_name)
        base_glyph.width = ufo.info.unitsPerEm

        # Setup access to the glyph
        if len(codepoints) == 1:
            base_glyph.unicode = next(iter(codepoints))
        else:
            # Multi-codepoint seq; need to setup an rlig => base glyph
            logging.warning('TODO prepare for rlig => glyph')

        # Grab the transform + (color, glyph) layers for COLR
        return  ColorGlyph(ufo,
                           filename,
                           glyph_name,
                           glyph_id,
                           codepoints,
                           nsvg)


    def transform_for_font_space(self):
        """Creates a Transform to map SVG coords to font coords"""
        view_box = self.nsvg.view_box()
        if view_box is None:
            logging.warning(f'{self.ufo.info.familyName} has no viewBox; no transform will be applied')
            return Transform()
        upem = self.ufo.info.unitsPerEm
        # shift so origin is 0,0
        dx = -view_box[0]
        dy = -view_box[1]
        x_scale = round(upem / abs(view_box[2] + dx), 3)
        y_scale = round(-1 * upem / abs(view_box[3] + dy), 3)
        transform = Transform(x_scale, 0, 0, y_scale, dx, dy)
        logging.debug('%s %s %s', self.ufo.info.familyName, self.glyph_name, transform)
        return transform

    def as_colored_layers(self):
        """Yields (Color, SVGPath) tuples to draw nsvg."""
        for shape in self.nsvg.shapes():
            yield (_color(shape), shape)

    def colors(self):
        """Set of Color used by this glyph."""
        return {_color(shape) for shape in self.nsvg.shapes()}
