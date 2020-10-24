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
from fontTools import ttLib
from graphviz import Digraph
from typing import Set, Tuple


FLAGS = flags.FLAGS


class DAG:
    graph: Digraph
    edges: Set[Tuple[str, str]]

    def __init__(self):
        self.graph = Digraph("unix", directory="build", format="svg", graph_attr = {"rankdir": "LR"})
        self.edges = set()

    def edge(self, src, dest):
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


def _paint(dag, parent, font, paint, depth):
    palette = font["CPAL"].palettes[0]

    if paint.Format == 1:
        name = f"Solid_{palette[paint.Color.PaletteIndex]}_{paint.Color.Alpha.value:.4f}"
        print(_indent(depth), name)
    elif paint.Format == 2:
        name = "PaintLinearGradient"
        print(_indent(depth), name)
    elif paint.Format == 3:
        name = "PaintRadialGradient"
        print(_indent(depth), name)
    elif paint.Format == 4:
        name = "Glyph_" + paint.Glyph
        print(_indent(depth), name)
        _paint(dag, name, font, paint.Paint, depth + 1)
    elif paint.Format == 5:
        name = "Colr_" + paint.Glyph
        print(_indent(depth), name)
        _glyph(dag, name, font, _only(_base_glyphs(font, lambda g: g.BaseGlyph == paint.Glyph)), depth + 1)
    elif paint.Format == 6:
        name = "PaintTransformed"
        print(_indent(depth), name)
    elif paint.Format == 7:
        name = "PaintComposite"
        print(_indent(depth), name)

    dag.edge(parent, name)


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
