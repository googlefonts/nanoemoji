from absl import logging
from fontTools.misc.transform import Transform
import collections
from colors import Color
from itertools import chain
from lxml import etree
from paint import ColorStop, PaintLinearGradient, PaintSolid
import regex


def _glyph_name(codepoints):
    return 'emoji_' + '_'.join(('%04x' % c for c in codepoints))


def _color_stop(stop_el):
    offset = stop_el.attrib.get('offset', '0%')
    if not offset.endswith('%'):
        raise ValueError('Only offset %% supported')
    color = stop_el.attrib.get('stop-color', 'black')
    if 'stop-opacity' in stop_el.attrib:
        raise ValueError('<stop stop-opacity/> not supported')
    return ColorStop(stopOffset=int(offset[:-1]) / 100, color=Color.fromstring(color))


def _paint(nsvg, shape):
    match = regex.match(r'^url[(]#([^)]+)[)]$', shape.fill)
    if shape.fill.startswith('url('):
        el = nsvg.resolve_url(shape.fill, '*')
        tag = etree.QName(el).localname

        if tag == 'linearGradient':
            if set(el.attrib.keys()) != {'id'}:
                raise ValueError('Only @id supported for linearGradient')
            return PaintLinearGradient(stops=tuple(_color_stop(stop) for stop in el))
        elif tag == 'radialGradient':
            logging.warning('TODO process radialGradient %s', shape.fill)
            raise ValueError(f'Unable to handle {el.tag}')
        else:
            raise ValueError(f'Unable to handle {el.tag}')
    return PaintSolid(color=Color.fromstring(shape.fill, alpha=shape.opacity))


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
        # scale to font upem
        x_scale = round(upem / abs(view_box[2] + dx), 3)
        y_scale = round(upem / abs(view_box[3] + dy), 3)
        # flip y axis and shift so things are in the right place
        y_scale = -y_scale
        dy = dy + upem
        transform = Transform(x_scale, 0, 0, y_scale, dx, dy)
        logging.debug('%s %s %s', self.ufo.info.familyName, self.glyph_name, transform)
        return transform

    def as_painted_layers(self):
        """Yields (Paint, SVGPath) tuples to draw nsvg."""
        for shape in self.nsvg.shapes():
            yield (_paint(self.nsvg, shape), shape)

    def paints(self):
        """Set of Paint used by this glyph."""
        return {_paint(self.nsvg, shape) for shape in self.nsvg.shapes()}

    def colors(self):
        """Set of Color used by this glyph."""
        return set(chain.from_iterable([p.colors() for p in self.paints()]))
