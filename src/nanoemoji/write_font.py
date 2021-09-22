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
from collections import Counter
import csv
import dataclasses
import math
from fontTools import ttLib
from fontTools.misc.arrayTools import rectArea, normRect, unionRect
from fontTools.misc.roundTools import otRound
from fontTools.ttLib.tables import otTables as ot
from fontTools.pens.boundsPen import ControlBoundsPen
from fontTools.pens.transformPen import TransformPen
from itertools import chain
from lxml import etree  # pytype: disable=import-error
from nanoemoji import codepoints, config
from nanoemoji.colors import Color
from nanoemoji.config import FontConfig
from nanoemoji.color_glyph import ColorGlyph
from nanoemoji.fixed import fixed_safe
from nanoemoji.glyph import glyph_name
from nanoemoji.glyph_reuse import GlyphReuseCache
from nanoemoji.paint import (
    is_gradient,
    is_transform,
    transformed,
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
    cast,
    Any,
    Callable,
    Generator,
    Iterable,
    Mapping,
    MutableSequence,
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
    apply_ufo: Callable[[FontConfig, ufoLib2.Font, MutableSequence[ColorGlyph]], None]
    apply_ttfont: Callable[
        [FontConfig, ufoLib2.Font, MutableSequence[ColorGlyph], ttLib.TTFont], None
    ]
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
        config, ufo, color_glyphs, ttfont
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


def _create_glyph(
    color_glyph: ColorGlyph, paint: PaintGlyph, path_in_font_space: str
) -> Glyph:
    glyph = _init_glyph(color_glyph)
    ufo = color_glyph.ufo
    draw_svg_path(SVGPath(d=path_in_font_space), glyph.getPen())
    ufo.glyphOrder += [glyph.name]
    return glyph


def _migrate_paths_to_ufo_glyphs(
    color_glyph: ColorGlyph, glyph_cache: GlyphReuseCache
) -> ColorGlyph:
    svg_units_to_font_units = color_glyph.transform_for_font_space()

    # Walk through the color glyph, where we see a PaintGlyph take the path out of it,
    # move the path into font coordinates, generate a ufo glyph, and push the name of
    # the ufo glyph into the PaintGlyph
    def _update_paint_glyph(paint):
        if paint.format != PaintGlyph.format:
            return paint

        if glyph_cache.is_known_glyph(paint.glyph):
            return paint

        assert paint.glyph.startswith("M"), f"{paint.glyph} doesn't look like a path"
        path_in_font_space = (
            SVGPath(d=paint.glyph).apply_transform(svg_units_to_font_units).d
        )

        reuse_result = glyph_cache.try_reuse(path_in_font_space)
        if reuse_result is not None:
            # TODO: when is it more compact to use a new transforming glyph?
            child_transform = Affine2D.identity()
            child_paint = paint.paint
            if is_transform(child_paint):
                child_transform = child_paint.gettransform()
                child_paint = child_paint.paint

            # sanity check: GlyphReuseCache.try_reuse would return None if overflowed
            assert fixed_safe(*reuse_result.transform)
            overflows = False

            # TODO: handle gradient anywhere in subtree, not only as direct child of
            # PaintGlyph or PaintTransform
            if is_gradient(child_paint):
                # We have a gradient so we need to reverse the effect of the
                # reuse_result.transform. First we try to apply the combined transform
                # to the gradient's geometry; but this may overflow OT integer bounds,
                # in which case we pass through gradient unscaled
                transform = Affine2D.compose_ltr(
                    (child_transform, reuse_result.transform.inverse())
                )
                # skip reuse if combined transform overflows OT int bounds
                overflows = not fixed_safe(*transform)
                if not overflows:
                    try:
                        child_paint = child_paint.apply_transform(transform)
                    except OverflowError:
                        child_paint = transformed(transform, child_paint)

            if not overflows:
                return transformed(
                    reuse_result.transform,
                    PaintGlyph(
                        glyph=reuse_result.glyph_name,
                        paint=child_paint,
                    ),
                )

        glyph = _create_glyph(color_glyph, paint, path_in_font_space)
        glyph_cache.add_glyph(glyph.name, path_in_font_space)

        return dataclasses.replace(paint, glyph=glyph.name)

    return color_glyph.mutating_traverse(_update_paint_glyph)


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


def _glyf_ufo(
    config: FontConfig, ufo: ufoLib2.Font, color_glyphs: MutableSequence[ColorGlyph]
):
    # glyphs by reuse_key
    glyph_cache = GlyphReuseCache(config.reuse_tolerance)
    glyph_uses = Counter()
    for i, color_glyph in enumerate(color_glyphs):
        logging.debug(
            "%s %s %s",
            ufo.info.familyName,
            color_glyph.glyph_name,
            color_glyph.transform_for_font_space(),
        )
        parent_glyph = ufo[color_glyph.glyph_name]

        # generate glyphs for PaintGlyph's and assign glyph names
        color_glyphs[i] = color_glyph = _migrate_paths_to_ufo_glyphs(
            color_glyph, glyph_cache
        )

        for root in color_glyph.painted_layers:
            for context in root.breadth_first():
                # For 'glyf' just dump anything that isn't a PaintGlyph
                if not isinstance(context.paint, PaintGlyph):
                    continue
                paint_glyph = cast(PaintGlyph, context.paint)
                glyph = ufo.get(paint_glyph.glyph)
                parent_glyph.components.append(
                    Component(baseGlyph=glyph.name, transformation=context.transform)
                )
                glyph_uses[glyph.name] += 1

    # No great reason to keep single-component glyphs around (unless reused)
    for color_glyph in color_glyphs:
        parent_glyph = ufo[color_glyph.glyph_name]
        if (
            len(parent_glyph.components) == 1
            and glyph_uses[parent_glyph.components[0].baseGlyph] == 1
        ):
            component = ufo[parent_glyph.components[0].baseGlyph]
            del ufo[component.name]
            component.unicode = parent_glyph.unicode
            ufo[color_glyph.glyph_name] = component
            assert component.name == color_glyph.glyph_name


def _name_prefix(color_glyph: ColorGlyph) -> Glyph:
    return f"{color_glyph.glyph_name}."


def _init_glyph(color_glyph: ColorGlyph) -> Glyph:
    ufo = color_glyph.ufo
    glyph = ufo.newGlyph(_next_name(ufo, lambda i: f"{_name_prefix(color_glyph)}{i}"))
    glyph.width = ufo.get(color_glyph.glyph_name).width
    return glyph


def _init_glyph(color_glyph: ColorGlyph) -> Glyph:
    ufo = color_glyph.ufo
    glyph = ufo.newGlyph(_next_name(ufo, lambda i: f"{_name_prefix(color_glyph)}{i}"))
    glyph.width = ufo.get(color_glyph.glyph_name).width
    return glyph


def _create_transformed_glyph(
    color_glyph: ColorGlyph, paint: PaintGlyph, transform: Affine2D
) -> Glyph:
    glyph = _init_glyph(color_glyph)
    glyph.components.append(Component(baseGlyph=paint.glyph, transformation=transform))
    color_glyph.ufo.glyphOrder += [glyph.name]
    return glyph


def _colr0_layers(color_glyph: ColorGlyph, root: Paint, palette: Sequence[Color]):
    # COLRv0: write out each PaintGlyph we see in it's first color
    # If we see a transformed glyph generate a component
    # Results for complex structures will be suboptimal :)
    ufo = color_glyph.ufo
    layers = []
    for context in root.breadth_first():
        if context.paint.format != PaintGlyph.format:  # pytype: disable=attribute-error
            continue
        paint_glyph: PaintGlyph = (
            context.paint
        )  # pytype: disable=annotation-type-mismatch
        color = next(paint_glyph.colors())
        glyph_name = paint_glyph.glyph

        if context.transform != Affine2D.identity():
            glyph_name = _create_transformed_glyph(
                color_glyph, paint_glyph, context.transform
            ).name

        layers.append((glyph_name, palette.index(color)))
    return layers


def _quantize_bounding_rect(
    xMin: float,
    yMin: float,
    xMax: float,
    yMax: float,
    factor: int = 1,
) -> Tuple[int, int, int, int]:
    """
    >>> bounds = (72.3, -218.4, 1201.3, 919.1)
    >>> _quantize_bounding_rect(*bounds)
    (72, -219, 1202, 920)
    >>> _quantize_bounding_rect(*bounds, factor=10)
    (70, -220, 1210, 920)
    >>> _quantize_bounding_rect(*bounds, factor=100)
    (0, -300, 1300, 1000)
    """
    assert factor >= 1
    return (
        int(math.floor(xMin / factor) * factor),
        int(math.floor(yMin / factor) * factor),
        int(math.ceil(xMax / factor) * factor),
        int(math.ceil(yMax / factor) * factor),
    )


def _transformed_glyph_bounds(
    ufo: ufoLib2.Font, glyph_name: str, transform: Affine2D
) -> Optional[Tuple[float, float, float, float]]:
    glyph = ufo[glyph_name]
    pen = bounds_pen = ControlBoundsPen(ufo)
    if transform != Affine2D.identity():
        pen = TransformPen(bounds_pen, transform)
    glyph.draw(pen)
    return bounds_pen.bounds


def _bounds(
    color_glyph: ColorGlyph, quantize_factor: int = 1
) -> Optional[Tuple[int, int, int, int]]:
    bounds = None
    for root in color_glyph.painted_layers:
        for context in root.breadth_first():
            if not isinstance(context.paint, PaintGlyph):
                continue
            paint_glyph: PaintGlyph = cast(PaintGlyph, context.paint)
            glyph_bbox = _transformed_glyph_bounds(
                color_glyph.ufo, paint_glyph.glyph, context.transform
            )
            if glyph_bbox is None:
                continue
            if bounds is None:
                bounds = glyph_bbox
            else:
                bounds = unionRect(bounds, glyph_bbox)
    if bounds is None:
        return
    # before quantizing to integer values > 1, we must first round floats to
    # int using the same rounding function (i.e. otRound) that fontTools
    # glyf table's compile method will use to round any float coordinates.
    bounds = tuple(otRound(v) for v in bounds)
    if quantize_factor > 1:
        return _quantize_bounding_rect(*bounds, factor=quantize_factor)
    return bounds


def _ufo_colr_layers(colr_version, colors, color_glyph):
    # The value for a COLOR_LAYERS_KEY entry per
    # https://github.com/googlefonts/ufo2ft/pull/359
    colr_layers = []

    # accumulate layers in z-order
    for paint in color_glyph.painted_layers:
        if colr_version == 0:
            colr_layers.extend(_colr0_layers(color_glyph, paint, colors))
        elif colr_version == 1:
            colr_layers.append(paint.to_ufo_paint(colors))
        else:
            raise ValueError(f"Invalid color version {colr_version}")

    if colr_version > 0:
        colr_layers = {
            "Format": int(ot.PaintFormat.PaintColrLayers),
            "Layers": colr_layers,
        }

    return colr_layers


def _colr_ufo(colr_version, config, ufo, color_glyphs):
    # Sort colors so the index into colors == index into CPAL palette.
    # We only store opaque colors in CPAL for COLRv1, as 'alpha' is
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
    glyph_cache = GlyphReuseCache(config.reuse_tolerance)

    clipBoxes = {}
    quantization = config.clipbox_quantization
    if quantization is None:
        # by default, quantize clip boxes to an integer value 2% of the UPEM
        quantization = round(config.upem * 0.02)
    for i, color_glyph in enumerate(color_glyphs):
        logging.debug(
            "%s %s %s",
            ufo.info.familyName,
            color_glyph.glyph_name,
            color_glyph.transform_for_font_space(),
        )

        # generate glyphs for PaintGlyph's and assign glyph names
        color_glyphs[i] = color_glyph = _migrate_paths_to_ufo_glyphs(
            color_glyph, glyph_cache
        )

        # write out the ufo structures for COLR
        ufo_color_layers[color_glyph.glyph_name] = _ufo_colr_layers(
            colr_version, colors, color_glyph
        )
        bounds = _bounds(color_glyph, quantization)
        if bounds is not None:
            clipBoxes.setdefault(bounds, []).append(color_glyph.glyph_name)

    ufo.lib[ufo2ft.constants.COLOR_LAYERS_KEY] = ufo_color_layers
    if clipBoxes:
        if colr_version == 0:
            # COLRv0 doesn't define its own bounding boxes, but some implementations
            # rely on the extents of the base glyph so we must add those
            for bounds, glyphs in clipBoxes.items():
                for glyph_name in glyphs:
                    _draw_glyph_extents(ufo, ufo[glyph_name], bounds)
        else:
            # COLRv1 clip boxes are stored in UFO lib.plist as an array of 2-tuples,
            # each containing firstly the glyph names (array of strings), and secondly
            # the clip box values (array of 4 integers for a non-variable box) shared
            # by all those glyphs.
            ufo.lib[ufo2ft.constants.COLR_CLIP_BOXES_KEY] = [
                (glyphs, box) for box, glyphs in clipBoxes.items()
            ]


def _svg_ttfont(
    config: FontConfig, _, color_glyphs, ttfont, picosvg=True, compressed=False
):
    make_svg_table(config, ttfont, color_glyphs, picosvg, compressed)


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
    # TODO: Optimize glyphOrder so that color glyphs sharing the same clip box
    # values are placed next to one another in continuous ranges, to minimize number
    # of COLRv1 ClipRecords
    ufo.glyphOrder = ufo.glyphOrder + [g.glyph_name for g in color_glyphs]
    for g in color_glyphs:
        assert g.glyph_id == ufo.glyphOrder.index(g.glyph_name)

    _COLOR_FORMAT_GENERATORS[config.color_format].apply_ufo(config, ufo, color_glyphs)

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
