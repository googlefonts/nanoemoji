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

# TODO update to latest format #s; use consts to avoid this in future

from absl import app
from absl import flags
from absl import logging
from collections import Counter
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools import ttLib
from fontTools.ttLib.tables import otTables as ot
from graphviz import Digraph  # pytype: disable=import-error
from lxml import etree  # pytype: disable=import-error
from nanoemoji.colors import Color
from typing import Mapping, NamedTuple, Set, Tuple


FLAGS = flags.FLAGS


class Node(NamedTuple):
    node_id: str
    node_label: str = None

    def label(self):
        if self.node_label:
            return self.node_label
        return self.node_id


class DAG:
    graph: Digraph
    edges: Set[Tuple[str, str]]
    nth_of_type: Mapping[str, int]
    count_of_type: Counter

    def __init__(self):
        self.graph = Digraph(
            "unix", directory="build", format="svg", graph_attr={"rankdir": "LR"}
        )
        self.edges = set()
        self.nth_of_type = {}
        self.count_of_type = Counter()

    def visited(self, node_id):
        return node_id in self.nth_of_type

    def edge(self, src, dest):
        if not self.visited(dest):
            dest_type = dest
            if "_" in dest:
                dest_type = dest[: dest.index("_")]
            self.count_of_type[dest_type] += 1
            self.nth_of_type[dest] = self.count_of_type[dest_type]

            # if len(dest) > 32:
            #    self.graph.node(dest, f"{dest_type}.{self.nth_of_type[dest]}")
        new_edge = (src, dest) not in self.edges
        if src is not None and new_edge:
            self.graph.edge(src, dest)
        self.edges.add((src, dest))
        return new_edge


def _base_glyphs(font, filter_fn):
    for base_glyph in font["COLR"].table.BaseGlyphList.BaseGlyphPaintRecord:
        if filter_fn(base_glyph):
            yield base_glyph


def _only(seq):
    seq = tuple(seq)
    if len(seq) != 1:
        raise ValueError(f"Need 1 entry, got {len(seq)}")
    return seq[0]


def _indent(depth):
    return depth * "  "


def _color_index_node(palette, palette_index, ci_alpha):
    color = Color.fromstring(palette[palette_index].hex())
    node_id = f"{ci_alpha:.2f}.{color.opaque().to_string()}.{color.alpha:.2f}"
    return Node(
        node_id=node_id,
        node_label=color._replace(alpha=color.alpha * ci_alpha).to_string(),
    )


def _color_line_node(palette, color_line):
    id_parts = ["ColorLine", color_line.Extend.name]
    name_parts = id_parts[:]
    for stop in color_line.ColorStop:
        color_node = _color_index_node(palette, stop.PaletteIndex, stop.Alpha)
        id_parts.append(f"{color_node.node_id}@{stop.StopOffset:.1f}")
        name_parts.append(f"{color_node.node_label}@{stop.StopOffset:.1f}")
    return Node(node_id="_".join(id_parts), node_label=" ".join(name_parts))


def _paint_node(glyph_order, palette, paint) -> Node:
    if paint.Format == ot.PaintFormat.PaintColrLayers:
        return Node(
            node_id=(
                f"Layers_[{paint.FirstLayerIndex}..{paint.FirstLayerIndex+paint.NumLayers}]"
            )
        )
    if paint.Format == ot.PaintFormat.PaintSolid:
        return _color_index_node(palette, paint.PaletteIndex, paint.Alpha)
    if paint.Format == ot.PaintFormat.PaintLinearGradient:
        id_parts = (
            "Linear",
            f"p0({paint.x0}, {paint.y0})",
            f"p1({paint.x1}, {paint.y1})",
            f"p2({paint.x2}, {paint.y2})",
            _color_line_node(palette, paint.ColorLine).node_id,
        )
        return Node(node_id="_".join(id_parts), node_label=" ".join(id_parts[:-1]))
    if paint.Format == ot.PaintFormat.PaintRadialGradient:
        id_parts = (
            "Radial",
            f"c0({paint.x0}, {paint.y0})",
            f"r0 {paint.r0}",
            f"c1({paint.x1}, {paint.y1})",
            f"r1 {paint.r1}",
            _color_line_node(palette, paint.ColorLine).node_id,
        )
        return Node(node_id="_".join(id_parts), node_label=" ".join(id_parts[:-1]))
    if paint.Format == ot.PaintFormat.PaintGlyph:
        id_parts = (
            "Glyph",
            paint.Glyph,
            _paint_node(glyph_order, palette, paint.Paint).node_id,
        )
        return Node(
            node_id="_".join(id_parts),
            node_label=f"gid {glyph_order.index(paint.Glyph)}",
        )
    if paint.Format == ot.PaintFormat.PaintColrGlyph:
        id_parts = (
            "Base",
            paint.Glyph,
        )
        return Node(node_id="_".join(id_parts))
    if paint.Format == ot.PaintFormat.PaintTranslate:
        id_parts = (
            "Translate",
            f"dx {paint.dx}",
            f"dy {paint.dy}",
            _paint_node(glyph_order, palette, paint.Paint).node_id,
        )
        return Node(node_id="_".join(id_parts))
    if paint.Format == ot.PaintFormat.PaintTransform:
        id_parts = (
            "Transform",
            f"î {paint.Transform.xx},{paint.Transform.xy}",
            f"ĵ {paint.Transform.yx},{paint.Transform.yy}",
            f"dx {paint.Transform.dx}",
            f"dy {paint.Transform.dy}",
            _paint_node(glyph_order, palette, paint.Paint).node_id,
        )
        return Node(node_id="_".join(id_parts))
    if paint.Format == ot.PaintFormat.PaintComposite:
        id_parts = (
            "Composite",
            _paint_node(glyph_order, palette, paint.SourcePaint).node_id,
            paint.CompositeMode.name,
            _paint_node(glyph_order, palette, paint.BackdropPaint).node_id,
        )
        return Node(node_id="_".join(id_parts), node_label=paint.CompositeMode.name)

    raise NotImplementedError(f"id for format {paint.Format} ({dir(paint)})")


def _additional_log(font, paint):
    if paint.Format == ot.PaintFormat.PaintGlyph:
        glyph_name = paint.Glyph
        glyph_set = font.getGlyphSet()
        svg_pen = SVGPathPen(glyph_set)
        glyph_set[glyph_name].draw(svg_pen)
        return " " + f"<path d=\"{svg_pen.getCommands()}\" />"
    return ""


def _paint(dag, parent, font, paint, depth):
    if depth > 256:
        raise NotImplementedError("Too deep, something wrong?")
    palette = font["CPAL"].palettes[0]
    node = _paint_node(font.getGlyphOrder(), palette, paint)
    logging.info(_indent(depth) + node.label() + _additional_log(font, paint))

    dag.graph.node(node.node_id, node.node_label)

    node_id = node.node_id
    new_edge = dag.edge(parent, node_id)

    # Descend
    if new_edge:
        if paint.Format == ot.PaintFormat.PaintColrLayers:
            child_paints = font["COLR"].table.LayerList.Paint[
                paint.FirstLayerIndex : paint.FirstLayerIndex + paint.NumLayers
            ]
            for child_paint in child_paints:
                _paint(dag, node_id, font, child_paint, depth + 1)
        elif paint.Format == ot.PaintFormat.PaintSolid:
            pass
        elif paint.Format in (
            ot.PaintFormat.PaintLinearGradient,
            ot.PaintFormat.PaintRadialGradient,
        ):
            color_node = _color_line_node(palette, paint.ColorLine)
            dag.graph.node(color_node.node_id, color_node.node_label)
            dag.edge(node_id, color_node.node_id)
        elif paint.Format == ot.PaintFormat.PaintGlyph:
            _paint(dag, node_id, font, paint.Paint, depth + 1)
        # adding format 5 edges makes the result a horrible mess
        # elif paint.Format == 5:
        #   _glyph(dag, node_id, font, _only(_base_glyphs(font, lambda g: g.BaseGlyph == paint.Glyph)), depth + 1)
        elif paint.Format == ot.PaintFormat.PaintTranslate:
            _paint(dag, node_id, font, paint.Paint, depth + 1)
        elif paint.Format == ot.PaintFormat.PaintTransform:
            _paint(dag, node_id, font, paint.Paint, depth + 1)
        elif paint.Format == ot.PaintFormat.PaintComposite:
            _paint(dag, node_id, font, paint.BackdropPaint, depth + 1)
            _paint(dag, node_id, font, paint.SourcePaint, depth + 1)
        else:
            raise ValueError(f"Unsupported: {paint.Format}")


def _glyph(dag, parent, font, base_glyph, depth=0):
    name = "Base_" + base_glyph.BaseGlyph
    dag.edge(parent, name)

    logging.info(_indent(depth) + name)
    _paint(dag, name, font, base_glyph.Paint, depth + 1)


def main(argv):
    if len(argv) > 2:
        raise ValueError("Only expected non-flag is font file")
    font = ttLib.TTFont(argv[1])

    dag = DAG()

    for base_glyph in _base_glyphs(font, lambda _: True):
        _glyph(dag, None, font, base_glyph)

    logging.info("Count by type")
    for node_type, count in sorted(dag.count_of_type.items()):
        logging.info("  %s %s", node_type, count)
    output_file = dag.graph.render()
    tree = etree.parse(output_file)
    del tree.getroot().attrib["width"]
    del tree.getroot().attrib["height"]
    tree.write(output_file, pretty_print=True)
    logging.info("wrote %s", output_file)


if __name__ == "__main__":
    app.run(main)
