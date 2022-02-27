from fontTools.ttLib.tables import otTables as ot
from fontTools import ttLib
import os

_ORIGINAL="/tmp/Bungee7.ttf"
_COLR="/tmp/bungee7/AnEmojiFamily.ttf"

font = ttLib.TTFont(_ORIGINAL)
colr = ttLib.TTFont(_COLR)
_OUTPUT = '/tmp/bungee7/Bungee_SVG_COLR.ttf'

# Copy all glyphs used by COLR over
_glyphs_to_copy = set()

def _collect_glyphs(paint):
  if paint.Format == ot.PaintFormat.PaintGlyph:
    _glyphs_to_copy.add(paint.Glyph)

for record in colr["COLR"].table.BaseGlyphList.BaseGlyphPaintRecord:
  record.Paint.traverse(colr["COLR"].table, _collect_glyphs)

for glyph_name in _glyphs_to_copy:
  print("Copy glyph", glyph_name)
  font['glyf'].glyphs[glyph_name] = colr['glyf'].glyphs[glyph_name]
  font['hmtx'].metrics[glyph_name] = colr['hmtx'].metrics[glyph_name]
  font.getGlyphOrder().append(glyph_name)


# TODO what if CFF?


font['CPAL'] = colr['CPAL']
# save here is ok

font['COLR'] = colr['COLR']
font.save(_OUTPUT)
print("Wrote", _OUTPUT)