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

"""Writes a graphviz of a COLRv1 font."""

from absl import app
from absl import flags
from absl import logging
from collections import Counter
from fontTools import ttLib
from graphviz import Digraph
from typing import Mapping, Set, Tuple


FLAGS = flags.FLAGS


class DAG:
    graph: Digraph
    edges: Set[Tuple[str, str]]
    nth_of_type: Mapping[str, int]
    count_of_type: Counter

    def __init__(self):
        self.graph = Digraph("unix", directory="build", format="svg", graph_attr = {"rankdir": "LR"})
        self.edges = set()
        self.nth_of_type = {}
        self.count_of_type = Counter()

    def edge(self, src, dest):
        if dest not in self.nth_of_type:
            dest_type = dest[:dest.index("_")]
            self.count_of_type[dest_type] += 1
            self.nth_of_type[dest] = self.count_of_type[dest_type]

            #if len(dest) > 32:
            #    self.graph.node(dest, f"{dest_type}.{self.nth_of_type[dest]}")
        if src is not None and (src, dest) not in self.edges:
            self.graph.edge(src, dest)
            self.edges.add((src, dest))



def _base_glyphs(font, filter_fn):
    for base_glyph in font["COLR"].table.BaseGlyphV1List.BaseGlyphV1Record:
        if filter_fn(base_glyph):
            yield base_glyph


def _only(seq):
    seq = tuple(seq)
    if len(seq) != 1:
        raise ValueError("Need 1 entry, got " + len(seq))
    return seq[0]


def _indent(depth):
    return depth * "  "


def _color_line_node_id(palette, color_line):
    id_parts = ["ColorLine", color_line.Extend.name]
    for stop in color_line.ColorStop:
        cpal_color = palette[stop.Color.PaletteIndex]
        cpal_color = cpal_color._replace(alpha=int(cpal_color.alpha * stop.Color.Alpha.value))
        id_parts.append(f"{cpal_color.hex()}@{stop.StopOffset.value:.1f}")
    return "_".join(id_parts)

def _paint_node_id(palette, paint):
    if paint.Format == 1:
        cpal_color = palette[paint.Color.PaletteIndex]
        colr_alpha = paint.Color.Alpha.value
        return f"Solid_{cpal_color}_{colr_alpha:.4f}"
    if paint.Format == 2:
        id_parts = (
            "Linear",
            f"p0({paint.x0.value}, {paint.y0.value})",
            f"p1({paint.x1.value}, {paint.y1.value})",
            f"p2({paint.x2.value}, {paint.y2.value})",
            _color_line_node_id(palette, paint.ColorLine),
            )
        return "_".join(id_parts)
    if paint.Format == 3:
        id_parts = (
            "Radial",
            f"c0({paint.x0.value}, {paint.y0.value})",
            f"r0 {paint.r0.value}",
            f"c1({paint.x1.value}, {paint.y1.value})",
            f"r1 {paint.r1.value}",
            _color_line_node_id(palette, paint.ColorLine),
            )
        return "_".join(id_parts)
    if paint.Format == 4:
        return "Glyph_" + paint.Glyph
    if paint.Format == 5:
        return "Colr_" + paint.Glyph
    if paint.Format == 6:
        id_parts = (
            "Transform",
            f"î {paint.Transform.xx.value},{paint.Transform.xy.value}",
            f"ĵ {paint.Transform.yx.value},{paint.Transform.yy.value}",
            f"dx {paint.Transform.dx.value}",
            f"dy {paint.Transform.dy.value}",
            _paint_node_id(palette, paint.Paint),
            )
        return "_".join(id_parts)
    if paint.Format == 7:
        id_parts = (
            "Composite",
            _paint_node_id(palette, paint.SourcePaint),
            paint.CompositeMode.name,
            _paint_node_id(palette, paint.BackdropPaint),
            )
        return "_".join(id_parts)
    raise NotImplementedError(f"id for format {paint.Format} ({dir(paint)})")

def _paint(dag, parent, font, paint, depth):
    palette = font["CPAL"].palettes[0]
    node_id = _paint_node_id(palette, paint)
    print(_indent(depth), node_id)

    # if node_attr:
    #     dag.graph.node(name, **node_attr)
    dag.edge(parent, node_id)

    # Descend
    if paint.Format in (2, 3):
        dag.edge(node_id, _color_line_node_id(palette, paint.ColorLine))
    elif paint.Format == 4:
        _paint(dag, node_id, font, paint.Paint, depth + 1)
    elif paint.Format == 5:
        _glyph(dag, node_id, font, _only(_base_glyphs(font, lambda g: g.BaseGlyph == paint.Glyph)), depth + 1)
    elif paint.Format == 6:
        _paint(dag, node_id, font, paint.Paint, depth + 1)
    elif paint.Format == 7:
        _paint(dag, node_id, font, paint.BackdropPaint, depth + 1)
        _paint(dag, node_id, font, paint.SourcePaint, depth + 1)


def _glyph(dag, parent, font, base_glyph, depth=0):
    name = "Base_" + base_glyph.BaseGlyph
    dag.edge(parent, name)

    print(_indent(depth), name)
    for paint in base_glyph.LayerV1List.Paint:
        _paint(dag, name, font, paint, depth + 1)


def main(argv):
    if len(argv) > 2:
        raise ValueError("Only expected non-flag is font file")
    font = ttLib.TTFont(argv[1])

    dag = DAG()

    for base_glyph in _base_glyphs(font, lambda _: True):
        _glyph(dag, None, font, base_glyph)

    print("wrote", dag.graph.render())


if __name__ == "__main__":
    app.run(main)
