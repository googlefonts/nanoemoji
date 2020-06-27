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

"""Create an emoji font from a set of SVGs.

UFO handling informed by:
Cosimo's https://gist.github.com/anthrotype/2acbc67c75d6fa5833789ec01366a517
Notes for https://github.com/googlefonts/ufo2ft/pull/359

For COLR:
    Each SVG file represent one base glyph in the COLR font.
    For each glyph, we get a sequence of PaintedLayer.
    To convert to font format we  use the UFO Glyph pen.

Sample usage:
make_emoji_font.py -v 1 $(find ~/oss/noto-emoji/svg -name '*.svg')
make_emoji_font.py $(find ~/oss/twemoji/assets/svg -name '*.svg')
"""
from absl import app
from absl import flags
from absl import logging
import collections
from fontTools import ttLib
from fontTools.pens.transformPen import TransformPen
import io
from itertools import chain, groupby
from nanoemoji.colors import Color
from nanoemoji.color_glyph import ColorGlyph, PaintedLayer
from nanoemoji.glyph import glyph_name
from nanoemoji.paint import Paint
from nanoemoji.svg import make_svg_table
from picosvg.svg import SVG
from picosvg.svg_pathops import skia_path
from picosvg.svg_reuse import normalize, affine_between
from picosvg.svg_types import SVGPath
from picosvg.svg_transform import Affine2D
import os
import regex
import sys
from typing import Callable, Generator, Iterable, Mapping, NamedTuple, Sequence, Tuple
import ufoLib2
from ufoLib2.objects import Component, Glyph, Layer

import ufo2ft


class ColorFontConfig(NamedTuple):
    upem: int
    family: str
    color_format: str
    output_format: str
    keep_glyph_names: bool = False


class InputGlyph(NamedTuple):
    filename: str
    codepoints: Tuple[int, ...]
    picosvg: SVG


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
        lambda *_: None, lambda *args: _svg_ttfont(*args, picosvg=True, compressed=False), ".ttf"
    ),
    "picosvgz": ColorGenerator(
        lambda *_: None, lambda *args: _svg_ttfont(*args, picosvg=True, compressed=True), ".ttf"
    ),
    "untouchedsvg": ColorGenerator(
        lambda *_: None, lambda *args: _svg_ttfont(*args, picosvg=False, compressed=False), ".ttf"
    ),
    "untouchedsvgz": ColorGenerator(
        lambda *_: None, lambda *args: _svg_ttfont(*args, picosvg=False, compressed=True), ".ttf"
    ),
    "cbdt": ColorGenerator(
        lambda *args: _not_impl("ufo", *args),
        lambda *args: _not_impl("TTFont", *args),
        ".ttf",
    ),
    "sbix": ColorGenerator(
        lambda *args: _not_impl("ufo", *args),
        lambda *args: _not_impl("TTFont", *args),
        ".ttf",
    ),
}


FLAGS = flags.FLAGS


# TODO move to config file?
# TODO flag on/off shape reuse
flags.DEFINE_integer("upem", 1024, "Units per em.")
flags.DEFINE_string("family", "An Emoji Family", "Family name.")
flags.DEFINE_string("output_dir", "/tmp", "Where to put the output.")
flags.DEFINE_string(
    "output_file",
    None,
    "Output filename. By default derived from --output_dir and --family",
)
flags.DEFINE_enum(
    "color_format",
    "glyf_colr_0",
    sorted(_COLOR_FORMAT_GENERATORS.keys()),
    "Type of font to generate.",
)
flags.DEFINE_enum(
    "output", "font", ["ufo", "font"], "Whether to output a font binary or a UFO"
)
flags.DEFINE_bool(
    "keep_glyph_names", False, "Whether or not to store glyph names in the font."
)


def _codepoints_from_filename(filename):
    match = regex.search(r"(?:^emoji_u)?(?:[-_]?([0-9a-fA-F]{1,}))+", filename)
    if match:
        return tuple(int(s, 16) for s in match.captures(1))
    logging.warning(f"Bad filename {filename}; unable to extract codepoints")
    return None


def _picosvg(filename):
    try:
        return SVG.parse(filename).topicosvg()
    except Exception as e:
        logging.warning(f"SVG.parse({filename}) failed: {e}")
    return None


def _inputs(filenames: Iterable[str]) -> Generator[InputGlyph, None, None]:
    for filename in filenames:
        codepoints = _codepoints_from_filename(os.path.basename(filename))
        picosvg = _picosvg(filename)
        if codepoints and picosvg:
            yield InputGlyph(filename, codepoints, picosvg)


def _ufo(family: str, upem: int, keep_glyph_names: bool = False) -> ufoLib2.Font:
    ufo = ufoLib2.Font()
    ufo.info.familyName = family
    # set various font metadata; see the full list of fontinfo attributes at
    # http://unifiedfontobject.org/versions/ufo3/fontinfo.plist/
    ufo.info.unitsPerEm = upem

    # Must have .notdef and Win 10 Chrome likes a blank gid1 so make gid1 space
    ufo.newGlyph(".notdef")
    space = ufo.newGlyph(".space")
    space.unicodes = [0x0020]
    space.width = upem
    ufo.glyphOrder = [".notdef", ".space"]

    # use 'post' format 3.0 for TTFs, shaving a kew KBs of unneeded glyph names
    ufo.lib[ufo2ft.constants.KEEP_GLYPH_NAMES] = keep_glyph_names

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


def _not_impl(*_):
    raise NotImplementedError("%s not implemented" % FLAGS.color_format)


def _draw(source: SVGPath, dest: Glyph, svg_units_to_font_units: Affine2D):
    pen = TransformPen(dest.getPen(), svg_units_to_font_units)
    skia_path(source.as_cmd_seq()).draw(pen)


def _next_name(ufo: ufoLib2.Font, name_fn) -> str:
    i = 0
    while name_fn(i) in ufo:
        i += 1
    return name_fn(i)


def _create_glyph(color_glyph: ColorGlyph, painted_layer: PaintedLayer) -> Glyph:
    ufo = color_glyph.ufo

    glyph = ufo.newGlyph(_next_name(ufo, lambda i: f"{color_glyph.glyph_name}.{i}"))
    glyph_names = [glyph.name]
    glyph.width = ufo.info.unitsPerEm

    svg_units_to_font_units = color_glyph.transform_for_font_space()

    if painted_layer.reuses:
        # Shape repeats, form a composite
        base_glyph = ufo.newGlyph(
            _next_name(ufo, lambda i: f"{glyph.name}.component.{i}")
        )
        glyph_names.append(base_glyph.name)

        _draw(painted_layer.path, base_glyph, svg_units_to_font_units)

        glyph.components.append(
            Component(baseGlyph=base_glyph.name, transformation=Affine2D.identity())
        )

        for transform in painted_layer.reuses:
            # We already redrew the component into font space, don't redo it
            # scale x/y translation and flip y movement to match font space
            transform = transform._replace(
                e=transform.e * svg_units_to_font_units.a,
                f=transform.f * svg_units_to_font_units.d,
            )
            glyph.components.append(
                Component(baseGlyph=base_glyph.name, transformation=transform)
            )
    else:
        # Not a composite, just draw directly on the glyph
        _draw(painted_layer.path, glyph, svg_units_to_font_units)

    ufo.glyphOrder += glyph_names

    return glyph


def _draw_glyph_extents(ufo: ufoLib2.Font, glyph: Glyph):
    # apparently on Mac (but not Linux) Chrome and Firefox end up relying on the
    # extents of the base layer to determine where the glyph might paint. If you
    # leave the base blank the COLR glyph never renders.

    # TODO we could narrow this to bbox to cover all layers

    pen = glyph.getPen()
    pen.moveTo((0, 0))
    pen.lineTo((ufo.info.unitsPerEm, ufo.info.unitsPerEm))
    pen.endPath()

    return glyph


def _glyf_ufo(ufo, color_glyphs):
    # glyphs by reuse_key
    glyphs = {}
    for color_glyph in color_glyphs:
        logging.debug(
            "%s %s %s",
            ufo.info.familyName,
            color_glyph.glyph_name,
            color_glyph.transform_for_font_space(),
        )
        parent_glyph = ufo.get(color_glyph.glyph_name)
        for painted_layer in color_glyph.as_painted_layers():
            # if we've seen this shape before reuse it
            reuse_key = _inter_glyph_reuse_key(painted_layer)
            if reuse_key not in glyphs:
                glyph = _create_glyph(color_glyph, painted_layer)
                glyphs[reuse_key] = glyph
            else:
                glyph = glyphs[reuse_key]
            parent_glyph.components.append(Component(baseGlyph=glyph.name))

        # No great reason to keep single-component glyphs around
        if len(parent_glyph.components) == 1:
            component = ufo[parent_glyph.components[0].baseGlyph]
            del ufo[component.name]
            ufo[color_glyph.glyph_name] = component
            assert component.name == color_glyph.glyph_name


def _colr_paint(colr_version: int, paint: Paint, palette: Sequence[Color]):
    # For COLRv0, paint is just the palette index
    # For COLRv1, it's a data structure describing paint
    if colr_version == 0:
        # COLRv0: draw using the first available color on the glyph_layer
        # Results for gradients will be suboptimal :)
        color = next(paint.colors())
        return palette.index(color)

    elif colr_version == 1:
        # COLRv1: solid or gradient paint
        return paint.to_ufo_paint(palette)

    else:
        raise ValueError(f"Unsupported COLR version: {colr_version}")


def _inter_glyph_reuse_key(painted_layer: PaintedLayer):
    """Individual glyf entries, including composites, can be reused.

    COLR lets us reuse the shape regardless of paint so paint is not part of key."""
    return (painted_layer.path.d, painted_layer.reuses)


def _colr_ufo(colr_version, ufo, color_glyphs):
    # Sort colors so the index into colors == index into CPAL palette.
    # We only store opaque colors in CPAL for CORLv1, as 'transparency' is
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
    color_layers = {}

    # glyphs by reuse_key
    glyphs = {}
    for color_glyph in color_glyphs:
        logging.debug(
            "%s %s %s",
            ufo.info.familyName,
            color_glyph.glyph_name,
            color_glyph.transform_for_font_space(),
        )

        # The value for a COLOR_LAYERS_KEY entry per
        # https://github.com/googlefonts/ufo2ft/pull/359
        glyph_colr_layers = []

        # accumulate layers in z-order
        for painted_layer in color_glyph.as_painted_layers():
            # if we've seen this shape before reuse it
            reuse_key = _inter_glyph_reuse_key(painted_layer)
            if reuse_key not in glyphs:
                glyph = _create_glyph(color_glyph, painted_layer)
                glyphs[reuse_key] = glyph
            else:
                glyph = glyphs[reuse_key]

            paint = _colr_paint(colr_version, painted_layer.paint, colors)
            glyph_colr_layers.append((glyph.name, paint))

        colr_glyph = ufo.get(color_glyph.glyph_name)
        _draw_glyph_extents(ufo, colr_glyph)
        color_layers[colr_glyph.name] = glyph_colr_layers

    ufo.lib[ufo2ft.constants.COLOR_LAYERS_KEY] = color_layers


def _svg_ttfont(_, color_glyphs, ttfont, picosvg=True, compressed=False):
    make_svg_table(ttfont, color_glyphs, picosvg, compressed)


def _generate_fea(rgi_sequences):
    # TODO if this is a qualified sequence create the unqualified version and vice versa
    rules = []
    rules.append("languagesystem DFLT dflt;")
    rules.append("languagesystem latn dflt;")

    rules.append("feature rlig {")
    for rgi, target in sorted(rgi_sequences):
        if len(rgi) == 1:
            continue
        glyphs = [glyph_name(cp) for cp in rgi]
        rules.append("  sub %s by %s;" % (" ".join(glyphs), target))

    rules.append("} rlig;")
    return "\n".join(rules)


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


def _generate_color_font(config: ColorFontConfig, inputs: Iterable[InputGlyph]):
    """Make a UFO and optionally a TTFont from svgs."""
    ufo = _ufo(config.family, config.upem, config.keep_glyph_names)
    _ensure_codepoints_will_have_glyphs(ufo, inputs)

    base_gid = len(ufo.glyphOrder)
    color_glyphs = [
        ColorGlyph.create(ufo, filename, base_gid + idx, codepoints, psvg)
        for idx, (filename, codepoints, psvg) in enumerate(inputs)
    ]
    ufo.glyphOrder = ufo.glyphOrder + [g.glyph_name for g in color_glyphs]
    for g in color_glyphs:
        assert g.glyph_id == ufo.glyphOrder.index(g.glyph_name)

    _COLOR_FORMAT_GENERATORS[config.color_format].apply_ufo(ufo, color_glyphs)

    ufo.features.text = _generate_fea(
        [(c.codepoints, c.glyph_name) for c in color_glyphs]
    )
    logging.debug("fea:\n%s\n" % ufo.features.text)

    ttfont = _make_ttfont(config, ufo, color_glyphs)

    # TODO may wish to nuke 'post' glyph names

    return ufo, ttfont


def _run(argv):
    if FLAGS.output == "ufo":
        output_format = "ufo"
    else:
        output_format = _COLOR_FORMAT_GENERATORS[FLAGS.color_format].font_ext
    config = ColorFontConfig(
        upem=FLAGS.upem,
        family=FLAGS.family,
        color_format=FLAGS.color_format,
        output_format=output_format,
        keep_glyph_names=FLAGS.keep_glyph_names,
    )

    inputs = list(_inputs(argv[1:]))
    if not inputs:
        sys.exit("Please provide at least one svg filename")
    logging.info(f"{len(inputs)}/{len(argv[1:])} inputs prepared successfully")

    ufo, ttfont = _generate_color_font(config, inputs)

    output_file = FLAGS.output_file
    if output_file is None:
        output_file = f"{FLAGS.family.replace(' ', '')}{output_format}"
    output_file = os.path.join(FLAGS.output_dir, output_file)
    _write(ufo, ttfont, output_file)
    logging.info("Wrote %s" % output_file)


def main():
    # We don't seem to be __main__ when run as cli tool installed by setuptools
    app.run(_run)


if __name__ == "__main__":
    app.run(_run)
