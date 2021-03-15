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

"""Writes UFO and/or font files."""


from absl import app
from absl import flags
from absl import logging
from collections import defaultdict
import csv
from fontTools import ttLib
from fontTools.misc.arrayTools import rectArea, unionRect
from fontTools.ttLib.tables import otTables as ot
from itertools import chain
from lxml import etree  # pytype: disable=import-error
from nanoemoji import codepoints, config
from nanoemoji.colors import Color
from nanoemoji.config import FontConfig
from nanoemoji.color_glyph import ColorGlyph, PaintedLayer
from nanoemoji.glyph import glyph_name
from nanoemoji.paint import (
    CompositeMode,
    Paint,
    PaintComposite,
    PaintColrGlyph,
    PaintGlyph,
    PaintSolid,
)
from nanoemoji.svg import make_svg_table
from nanoemoji.svg_path import draw_svg_path
from nanoemoji import util
import os
from pathlib import Path
import ufoLib2
from picosvg.svg import SVG
from picosvg.svg_transform import Affine2D
from picosvg.svg_types import SVGPath
import regex
import sys
from typing import (
    Any,
    Callable,
    Generator,
    Iterable,
    Mapping,
    NamedTuple,
    Optional,
    Sequence,
    Tuple,
)
from ufoLib2.objects import Component, Glyph
import ufo2ft


FLAGS = flags.FLAGS


class InputGlyph(NamedTuple):
    filename: Path
    codepoints: Tuple[int, ...]
    svg: SVG  # picosvg except for untouched formats


# A color font generator.
#   apply_ufo(ufo, color_glyphs) is called first, to update a generated UFO
#   apply_ttfont(ufo, color_glyphs, ttfont) is called second, to allow fixups after ufo2ft
# Ideally we delete the ttfont stp in future. Blocking issues:
#   https://github.com/unified-font-object/ufo-spec/issues/104
# If the output file is .ufo then apply_ttfont is not called.
# Where possible code to the ufo and let apply_ttfont be a nop.
class ColorGenerator(NamedTuple):
    apply_ufo: Callable[[ufoLib2.Font, Sequence[ColorGlyph]], None]
    apply_ttfont: Callable[[ufoLib2.Font, Sequence[ColorGlyph], ttLib.TTFont], None]
    font_ext: str  # extension for font binary, .ttf or .otf


_COLOR_FORMAT_GENERATORS = {
    "glyf": ColorGenerator(lambda *args: _glyf_ufo(*args), lambda *_: None, ".ttf"),
    "glyf_colr_0": ColorGenerator(
        lambda *args: _colr_ufo(0, *args), lambda *_: None, ".ttf"
    ),
    "glyf_colr_1": ColorGenerator(
        lambda *args: _colr_ufo(1, *args), lambda *_: None, ".ttf"
    ),
    "cff_colr_0": ColorGenerator(
        lambda *args: _colr_ufo(0, *args), lambda *_: None, ".otf"
    ),
    "cff_colr_1": ColorGenerator(
        lambda *args: _colr_ufo(1, *args), lambda *_: None, ".otf"
    ),
    "cff2_colr_0": ColorGenerator(
        lambda *args: _colr_ufo(0, *args), lambda *_: None, ".otf"
    ),
    "cff2_colr_1": ColorGenerator(
        lambda *args: _colr_ufo(1, *args), lambda *_: None, ".otf"
    ),
    "picosvg": ColorGenerator(
        lambda *_: None,
        lambda *args: _svg_ttfont(*args, picosvg=True, compressed=False),
        ".ttf",
    ),
    "picosvgz": ColorGenerator(
        lambda *_: None,
        lambda *args: _svg_ttfont(*args, picosvg=True, compressed=True),
        ".ttf",
    ),
    "untouchedsvg": ColorGenerator(
        lambda *_: None,
        lambda *args: _svg_ttfont(*args, picosvg=False, compressed=False),
        ".ttf",
    ),
    "untouchedsvgz": ColorGenerator(
        lambda *_: None,
        lambda *args: _svg_ttfont(*args, picosvg=False, compressed=True),
        ".ttf",
    ),
    "cbdt": ColorGenerator(
        lambda *args: _not_impl("apply_ufo", "cbdt", *args),
        lambda *args: _not_impl("apply_ttfont", "cbdt", *args),
        ".ttf",
    ),
    "sbix": ColorGenerator(
        lambda *args: _not_impl("apply_ufo", "sbix", *args),
        lambda *args: _not_impl("apply_ttfont", "sbix", *args),
        ".ttf",
    ),
}
assert _COLOR_FORMAT_GENERATORS.keys() == set(config._COLOR_FORMATS)


def _ufo(config: FontConfig) -> ufoLib2.Font:
    ufo = ufoLib2.Font()
    ufo.info.familyName = config.family
    # set various font metadata; see the full list of fontinfo attributes at
    # https://unifiedfontobject.org/versions/ufo3/fontinfo.plist/#generic-dimension-information
    ufo.info.unitsPerEm = config.upem
    # we just use a simple scheme that makes all sets of vertical metrics the same;
    # if one needs more fine-grained control they can fix up post build
    ufo.info.ascender = (
        ufo.info.openTypeHheaAscender
    ) = ufo.info.openTypeOS2TypoAscender = config.ascender
    ufo.info.descender = (
        ufo.info.openTypeHheaDescender
    ) = ufo.info.openTypeOS2TypoDescender = config.descender
    ufo.info.openTypeHheaLineGap = ufo.info.openTypeOS2TypoLineGap = config.linegap
    # set USE_TYPO_METRICS flag (OS/2.fsSelection bit 7) to make sure OS/2 Typo* metrics
    # are preferred to define Windows line spacing over legacy WinAscent/WinDescent:
    # https://docs.microsoft.com/en-us/typography/opentype/spec/os2#fsselection
    ufo.info.openTypeOS2Selection = [7]

    # version
    ufo.info.versionMajor = config.version_major
    ufo.info.versionMinor = config.version_minor

    # Must have .notdef and Win 10 Chrome likes a blank gid1 so make gid1 space
    ufo.newGlyph(".notdef")
    space = ufo.newGlyph(".space")
    space.unicodes = [0x0020]
    space.width = config.width
    ufo.glyphOrder = [".notdef", ".space"]

    # use 'post' format 3.0 for TTFs, shaving a kew KBs of unneeded glyph names
    ufo.lib[ufo2ft.constants.KEEP_GLYPH_NAMES] = config.keep_glyph_names

    return ufo


def _make_ttfont(config, ufo, color_glyphs):
    if config.output_format == ".ufo":
        return None

    # Use skia-pathops to remove overlaps (i.e. simplify self-overlapping
    # paths) because the default ("booleanOperations") does not support
    # quadratic bezier curves (qcurve), which may appear
    # when we pass through picosvg (e.g. arcs or stroked paths).
    ttfont = None
    if config.output_format == ".ttf":
        ttfont = ufo2ft.compileTTF(ufo, overlapsBackend="pathops")
    if config.output_format == ".otf":
        cff_version = 1
        if config.color_format.startswith("cff2_"):
            cff_version = 2
        ttfont = ufo2ft.compileOTF(
            ufo, cffVersion=cff_version, overlapsBackend="pathops"
        )

    if not ttfont:
        raise ValueError(
            f"Unable to generate {config.color_format} {config.output_format}"
        )

    # Permit fixups where we can't express something adequately in UFO
    _COLOR_FORMAT_GENERATORS[config.color_format].apply_ttfont(
        ufo, color_glyphs, ttfont
    )

    return ttfont


def _write(ufo, ttfont, output_file):
    logging.info("Writing %s", output_file)

    if os.path.splitext(output_file)[1] == ".ufo":
        ufo.save(output_file, overwrite=True)
    else:
        ttfont.save(output_file)


def _not_impl(func_name, color_format, *_):
    raise NotImplementedError(f"{func_name} for {color_format} not implemented")


def _next_name(ufo: ufoLib2.Font, name_fn) -> str:
    i = 0
    while name_fn(i) in ufo:
        i += 1
    return name_fn(i)


def _create_glyph(color_glyph: ColorGlyph, painted_layer: PaintedLayer) -> Glyph:
    ufo = color_glyph.ufo

    glyph = ufo.newGlyph(_next_name(ufo, lambda i: f"{color_glyph.glyph_name}.{i}"))
    glyph_names = [glyph.name]
    glyph.width = ufo.get(color_glyph.glyph_name).width

    svg_units_to_font_units = color_glyph.transform_for_font_space()

    if painted_layer.reuses:
        # Shape repeats, form a composite
        base_glyph = ufo.newGlyph(
            _next_name(ufo, lambda i: f"{glyph.name}.component.{i}")
        )
        glyph_names.append(base_glyph.name)

        draw_svg_path(
            SVGPath(d=painted_layer.path), base_glyph.getPen(), svg_units_to_font_units
        )

        glyph.components.append(
            Component(baseGlyph=base_glyph.name, transformation=Affine2D.identity())
        )

        for transform in painted_layer.reuses:
            # We already drew the component into font space; transform is in SVG space
            transform = Affine2D.compose_ltr(
                (
                    svg_units_to_font_units.inverse(),
                    transform,
                    svg_units_to_font_units,
                )
            )
            glyph.components.append(
                Component(baseGlyph=base_glyph.name, transformation=transform)
            )
    else:
        # Not a composite, just draw directly on the glyph
        draw_svg_path(
            SVGPath(d=painted_layer.path), glyph.getPen(), svg_units_to_font_units
        )

    ufo.glyphOrder += glyph_names

    return glyph


def _draw_glyph_extents(
    ufo: ufoLib2.Font, glyph: Glyph, bounds: Tuple[float, float, float, float]
):
    # apparently on Mac (but not Linux) Chrome and Firefox end up relying on the
    # extents of the base layer to determine where the glyph might paint. If you
    # leave the base blank the COLR glyph never renders.

    if rectArea(bounds) == 0:
        return

    start, end = bounds[:2], bounds[2:]

    pen = glyph.getPen()
    pen.moveTo(start)
    pen.lineTo(end)
    pen.endPath()

    return glyph


def _glyf_ufo(ufo, color_glyphs):
    # glyphs by reuse_key
    glyphs = {}
    reused = set()
    for color_glyph in color_glyphs:
        logging.debug(
            "%s %s %s",
            ufo.info.familyName,
            color_glyph.glyph_name,
            color_glyph.transform_for_font_space(),
        )
        parent_glyph = ufo[color_glyph.glyph_name]
        for painted_layer in color_glyph.painted_layers:
            # if we've seen this shape before reuse it
            reuse_key = painted_layer.shape_cache_key()
            if reuse_key not in glyphs:
                glyph = _create_glyph(color_glyph, painted_layer)
                glyphs[reuse_key] = glyph
            else:
                glyph = glyphs[reuse_key]
                reused.add(glyph.name)
            parent_glyph.components.append(Component(baseGlyph=glyph.name))

    for color_glyph in color_glyphs:
        parent_glyph = ufo[color_glyph.glyph_name]
        # No great reason to keep single-component glyphs around (unless reused)
        if (
            len(parent_glyph.components) == 1
            and parent_glyph.components[0].baseGlyph not in reused
        ):
            component = ufo[parent_glyph.components[0].baseGlyph]
            del ufo[component.name]
            component.unicode = parent_glyph.unicode
            ufo[color_glyph.glyph_name] = component
            assert component.name == color_glyph.glyph_name


def _colr_layer(
    colr_version: int, layer_glyph_name: str, paint: Paint, palette: Sequence[Color]
):
    # For COLRv0, paint is just the palette index
    # For COLRv1, it's a data structure describing paint
    if colr_version == 0:
        # COLRv0: draw using the first available color on the glyph_layer
        # Results for gradients will be suboptimal :)
        color = next(paint.colors())
        return (layer_glyph_name, palette.index(color))

    elif colr_version == 1:
        # COLRv1: layer is graph of (solid, gradients, etc.) paints.
        # Root node is always a PaintGlyph (format 4) for now.
        # TODO Support more paints (PaintTransform, PaintColorGlyph, PaintComposite)
        return PaintGlyph(layer_glyph_name, paint).to_ufo_paint(palette)

    else:
        raise ValueError(f"Unsupported COLR version: {colr_version}")


def _inter_glyph_reuse_key(painted_layer: PaintedLayer) -> PaintedLayer:
    """Individual glyf entries, including composites, can be reused.

    COLR lets us reuse the shape regardless of paint so paint is not part of key."""
    return painted_layer._replace(paint=PaintSolid())


def _ufo_colr_layers_and_bounds(colr_version, colors, color_glyph, glyph_cache):
    # The value for a COLOR_LAYERS_KEY entry per
    # https://github.com/googlefonts/ufo2ft/pull/359
    colr_layers = []

    bounds = None
    # accumulate layers in z-order
    for painted_layer in color_glyph.painted_layers:
        # if we've seen this shape before reuse it
        glyph_cache_key = _inter_glyph_reuse_key(painted_layer)
        if glyph_cache_key not in glyph_cache:
            glyph = _create_glyph(color_glyph, painted_layer)
            glyph_cache[glyph_cache_key] = glyph
        else:
            glyph = glyph_cache[glyph_cache_key]

        glyph_bbox = glyph.getControlBounds(color_glyph.ufo)
        if glyph_bbox is not None:
            if bounds is None:
                bounds = glyph_bbox
            else:
                bounds = unionRect(bounds, glyph_bbox)

        layer = _colr_layer(colr_version, glyph.name, painted_layer.paint, colors)

        colr_layers.append(layer)

    if colr_version > 0:
        colr_layers = {
            "Format": int(ot.PaintFormat.PaintColrLayers),
            "Layers": colr_layers,
        }

    return colr_layers, bounds


def _colr_ufo(colr_version, ufo, color_glyphs):
    # Sort colors so the index into colors == index into CPAL palette.
    # We only store opaque colors in CPAL for CORLv1, as 'alpha' is
    # encoded separately.
    colors = sorted(
        set(
            c if colr_version == 0 else c.opaque()
            for c in chain.from_iterable(g.colors() for g in color_glyphs)
        )
    )
    logging.debug("colors %s", colors)

    # KISS; use a single global palette
    ufo.lib[ufo2ft.constants.COLOR_PALETTES_KEY] = [[c.to_ufo_color() for c in colors]]

    # each base glyph maps to a list of (glyph name, paint info) in z-order
    ufo_color_layers = {}

    # potentially reusable glyphs
    glyph_cache = {}

    # write out the glyphs
    for color_glyph in color_glyphs:
        logging.debug(
            "%s %s %s",
            ufo.info.familyName,
            color_glyph.glyph_name,
            color_glyph.transform_for_font_space(),
        )

        ufo_color_layers[color_glyph.glyph_name], bounds = _ufo_colr_layers_and_bounds(
            colr_version, colors, color_glyph, glyph_cache
        )
        if bounds is not None:
            colr_glyph = ufo.get(color_glyph.glyph_name)
            _draw_glyph_extents(ufo, colr_glyph, bounds)

    ufo.lib[ufo2ft.constants.COLOR_LAYERS_KEY] = ufo_color_layers


def _svg_ttfont(_, color_glyphs, ttfont, picosvg=True, compressed=False):
    make_svg_table(ttfont, color_glyphs, picosvg, compressed)


def _ensure_codepoints_will_have_glyphs(ufo, glyph_inputs):
    """Ensure all codepoints we use will have a glyph.

    Single codepoint sequences will directly mapped to their glyphs.
    We need to add a glyph for any codepoint that is only used in a multi-codepoint sequence.

    """
    all_codepoints = set()
    direct_mapped_codepoints = set()
    for _, codepoints, _ in glyph_inputs:
        if len(codepoints) == 1:
            direct_mapped_codepoints.update(codepoints)
        all_codepoints.update(codepoints)

    need_blanks = all_codepoints - direct_mapped_codepoints
    logging.debug("%d codepoints require blanks", len(need_blanks))
    glyph_names = []
    for codepoint in need_blanks:
        # Any layer is fine; we aren't going to draw
        glyph = ufo.newGlyph(glyph_name(codepoint))
        glyph.unicode = codepoint
        glyph_names.append(glyph.name)

    ufo.glyphOrder = ufo.glyphOrder + sorted(glyph_names)


def _generate_color_font(config: FontConfig, inputs: Iterable[InputGlyph]):
    """Make a UFO and optionally a TTFont from svgs."""
    ufo = _ufo(config)
    _ensure_codepoints_will_have_glyphs(ufo, inputs)
    base_gid = len(ufo.glyphOrder)
    color_glyphs = [
        ColorGlyph.create(config, ufo, filename, base_gid + idx, codepoints, svg)
        for idx, (filename, codepoints, svg) in enumerate(inputs)
    ]
    ufo.glyphOrder = ufo.glyphOrder + [g.glyph_name for g in color_glyphs]
    for g in color_glyphs:
        assert g.glyph_id == ufo.glyphOrder.index(g.glyph_name)

    _COLOR_FORMAT_GENERATORS[config.color_format].apply_ufo(ufo, color_glyphs)

    with open(config.fea_file) as f:
        ufo.features.text = f.read()
    logging.debug("fea:\n%s\n" % ufo.features.text)

    ttfont = _make_ttfont(config, ufo, color_glyphs)

    # TODO may wish to nuke 'post' glyph names

    return ufo, ttfont


def _inputs(
    codepoints: Mapping[str, Tuple[int, ...]], svg_files: Iterable[Path]
) -> Generator[InputGlyph, None, None]:
    for svg_file in svg_files:
        rgi = codepoints.get(svg_file.name, None)
        if not rgi:
            raise ValueError(f"No codepoint sequence for {svg_file}")
        try:
            picosvg = SVG.parse(str(svg_file))
        except etree.ParseError as e:
            raise IOError(f"Unable to parse {svg_file}") from e
        yield InputGlyph(svg_file, rgi, picosvg)


def _codepoint_map(codepoint_csv):
    return {name: rgi for name, rgi in codepoints.parse_csv(codepoint_csv)}


def main(argv):
    font_config = config.load()
    if len(font_config.masters) != 1:
        raise ValueError("write_font expects only one master")

    codepoints = _codepoint_map(font_config.codepointmap_file)
    inputs = list(_inputs(codepoints, font_config.masters[0].sources))
    if not inputs:
        sys.exit("Please provide at least one svg filename")
    ufo, ttfont = _generate_color_font(font_config, inputs)
    _write(ufo, ttfont, font_config.output_file)
    logging.info("Wrote %s" % font_config.output_file)


if __name__ == "__main__":
    app.run(main)
