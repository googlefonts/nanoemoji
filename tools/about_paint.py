from collections import Counter
import copy
from fontTools.colorLib.builder import LayerListBuilder
from fontTools.ttLib import TTFont
from fontTools.ttLib.tables import otTables as ot
from collections import defaultdict
from itertools import groupby
import logging
from math import acos, asin, atan, degrees
from nanoemoji.fixed import *
from picosvg.svg_transform import Affine2D
import os
import sys

def traverse_paint(colr, callback):
    """Traverse and optionally rewrite Paint in a COLRv1 graph."""
    if not callable(callback):
        raise TypeError("callback must be callable")

    visited = set()
    frontier = []
    # Glyph graphs start from either base glyphs or the layerlist
    for base_glyph in colr.BaseGlyphList.BaseGlyphPaintRecord:
        frontier.append((base_glyph, base_glyph.Paint))
    for paint in colr.LayerList.Paint:
        frontier.append((colr.LayerList.Paint, paint))
    while frontier:
        container, paint = frontier.pop()
        key = (id(container), id(paint))
        if key in visited:
            continue
        visited.add(key)

        new_paint = callback(paint)
        if new_paint is not None and new_paint is not paint:
            # replace existing paint
            did_replace = False
            if isinstance(container, list):
                idx = container.index(paint)
                container[idx] = new_paint
                did_replace = True
            else:
                for conv in container.getConverters():
                    value = getattr(container, conv.name, None)
                    if value is paint:
                        setattr(container, new_paint)
                        did_replace = True
            if not did_replace:
                raise ValueError("Unable to replace, no current field found")
            paint = new_paint
        frontier.extend((paint, c) for c in reversed(paint.getChildren(colr)))


def _angle(arcfn, v):
    return round(degrees(arcfn(v)), 4)


def _common_angle(a, b, c, d):
    return (
        all(-1 <= v <= 1 for v in (a, b, c, d))
        and len({
            _angle(acos, a),
            _angle(asin, b),
            _angle(lambda v: -asin(v), c),
            _angle(acos, d)
        }) == 1
    )

colr_builder = LayerListBuilder()

assert len(sys.argv) == 2
font = TTFont(sys.argv[1], lazy=False)
colr = font["COLR"].table
colr_data = font.reader["COLR"]

opportunities = []

count_by_type = Counter()
unique_dropped_affines = set()

visited = set()
def _about_paint(paint):
    hashable = colr_builder._paint_tuple(paint)
    if hashable in visited:
        return
    visited.add(hashable)

    count_by_type[paint.getFormatName()] += 1

    if paint.getFormatName() == 'PaintTransform':
        tr = paint.Transform
        transform = (tr.xx, tr.yx, tr.xy, tr.yy, tr.dx, tr.dy)
        # just scale and/or translate?
        if tr.xy == 0 and tr.yx == 0:
            # Relationship between scale and translate leads to div 0?
            if ((tr.xx == 1) != (tr.dx == 0)) or ((tr.yy == 1) != (tr.dy == 0)):
                count_by_type[paint.getFormatName() + "::weird_scale"] += 1
            elif f2dot14_safe(tr.xx, tr.yy):
                cx = cy = 0
                if tr.dx != 0:
                    cx = tr.dx / (1 - tr.xx)
                if tr.dy != 0:
                    cy = tr.dy / (1 - tr.yy)

                if int16_safe(cx, cy):
                    if tr.dx == 0 and tr.dy == 0:
                        count_by_type[paint.getFormatName() + "::scale_origin"] += 1
                    else:
                        count_by_type[paint.getFormatName() + "::scale_around"] += 1
                    unique_dropped_affines.add(transform)
                else:
                    count_by_type[paint.getFormatName() + "::scale_around_non_int"] += 1
            else:
                count_by_type[paint.getFormatName() + "::large_scale"] += 1
        else:
            translate, other = Affine2D(*transform).decompose_translation()
            if _common_angle(*other[:4]):
                if translate.almost_equals(Affine2D.identity()):
                    count_by_type[paint.getFormatName() + "::pure_rotate"] += 1
                else:
                    count_by_type[paint.getFormatName() + "::move_rotate"] += 1
            elif (tr.dx, tr.dy) == (0, 0):
                count_by_type[paint.getFormatName() + "::inexplicable_2x2"] += 1
            else:
                count_by_type[paint.getFormatName() + "::inexplicable_2x3"] += 1


traverse_paint(colr, _about_paint)

for format_name, count in sorted(count_by_type.items()):
    print(format_name, count)
print(f"PaintTransforms that should be upgraded have {len(unique_dropped_affines)} unique Affine2x3.")


