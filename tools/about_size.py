from about_paint import traverse_paint
from fontTools.ttLib import TTFont
from fontTools.ttLib.tables import otTables as ot
import os
import sys


def _extra_glyf(font, glyf):
    return f"{len(font.getGlyphOrder())} glyphs"


def _glyphs_in_COLR(colr):
    glyphs = set()

    visited = set()
    def _traverse_callback(paint):
        if paint.Format == ot.PaintFormat.PaintGlyph:
            glyphs.add(paint.Glyph)

    traverse_paint(colr, _traverse_callback)

    return glyphs


def _extra_COLR(font, colr):
    colr = colr.table
    glyphs = _glyphs_in_COLR(colr)
    return f"{len(glyphs)} glyphs"




assert len(sys.argv) == 2
font = TTFont(sys.argv[1], lazy=False)

file_size = os.stat(sys.argv[1]).st_size

for tag in font.keys():
    if len(tag) != 4:
        continue
    table_size = len(font.reader[tag])
    table_pct = 100. * table_size / file_size

    extra = globals().get(f"_extra_{tag.strip()}", lambda *_: "")(font, font[tag])

    print(f"{tag} {table_size:>6} {table_pct: >4.0f} {extra}")

colr = font["COLR"].table
colr_data = font.reader["COLR"]



