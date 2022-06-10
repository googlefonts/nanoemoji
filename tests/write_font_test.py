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


import dataclasses
import enum
import shutil
from pathlib import Path
from nanoemoji import write_font
from nanoemoji.colr import paints_of_type
from nanoemoji.config import _DEFAULT_CONFIG
from nanoemoji.glyphmap import GlyphMapping
from picosvg.svg_transform import Affine2D
from ufo2ft.constants import COLR_CLIP_BOXES_KEY
from fontTools.ttLib.tables import otTables as ot
from picosvg.svg import SVG
import pytest
import test_helper


@pytest.mark.parametrize(
    "svgs", [("rect.svg", "rect2.svg"), ("one-o-clock.svg", "two-o-clock.svg")]
)
@pytest.mark.parametrize(
    "color_format", ["glyf_colr_0", "glyf_colr_1", "picosvg", "untouchedsvg"]
)
@pytest.mark.parametrize("keep_glyph_names", [True, False])
def test_keep_glyph_names(svgs, color_format, keep_glyph_names):
    config, glyph_inputs = test_helper.color_font_config(
        {"color_format": color_format, "keep_glyph_names": keep_glyph_names}, svgs
    )
    ufo, ttfont = write_font._generate_color_font(config, glyph_inputs)
    ttfont = test_helper.reload_font(ttfont)

    assert len(ufo.glyphOrder) == len(ttfont.getGlyphOrder())
    if keep_glyph_names:
        assert ttfont["post"].formatType == 2.0
        assert ufo.glyphOrder == ttfont.getGlyphOrder()
    else:
        assert ttfont["post"].formatType == 3.0
        assert ufo.glyphOrder != ttfont.getGlyphOrder()


@pytest.mark.parametrize(
    "color_format",
    [
        "glyf",
        "cff_colr_0",
        "glyf_colr_1",
        "picosvg",
    ],
)
@pytest.mark.parametrize(
    "version_major, version_minor, expected",
    [
        (None, None, "1.000"),  # default
        (1, 2, "1.002"),
        (None, 1, "1.001"),
        (2, None, "2.000"),
        (16, 28, "16.028"),
        (16, 280, "16.280"),
    ],
)
def test_version(color_format, version_major, version_minor, expected):
    config_overrides = {"color_format": color_format}
    if version_major is not None:
        config_overrides["version_major"] = version_major
    else:
        version_major = 1
    if version_minor is not None:
        config_overrides["version_minor"] = version_minor
    else:
        version_minor = 0

    config, glyph_inputs = test_helper.color_font_config(
        config_overrides, ("rect.svg", "one-o-clock.svg")
    )
    ufo, ttfont = write_font._generate_color_font(config, glyph_inputs)
    ttfont = test_helper.reload_font(ttfont)

    assert ufo.info.versionMajor == version_major
    assert ufo.info.versionMinor == version_minor
    assert ttfont["name"].getDebugName(nameID=5).startswith(f"Version {expected}")


@pytest.mark.parametrize(
    "ascender, descender, linegap",
    [
        (
            _DEFAULT_CONFIG.ascender,
            _DEFAULT_CONFIG.descender,
            _DEFAULT_CONFIG.linegap,
        ),
        (1024, 0, 0),
        (820, -204, 200),
    ],
)
def test_vertical_metrics(ascender, descender, linegap):
    config_overrides = {
        "ascender": ascender,
        "descender": descender,
        "linegap": linegap,
    }
    config, glyph_inputs = test_helper.color_font_config(
        config_overrides, ("rect.svg", "one-o-clock.svg")
    )
    ufo, ttfont = write_font._generate_color_font(config, glyph_inputs)
    ttfont = test_helper.reload_font(ttfont)

    hhea = ttfont["hhea"]
    os2 = ttfont["OS/2"]

    assert ufo.info.ascender == hhea.ascent == os2.sTypoAscender == ascender
    assert ufo.info.descender == hhea.descent == os2.sTypoDescender == descender
    assert hhea.lineGap == os2.sTypoLineGap == linegap
    # check USE_TYPO_METRICS is set
    assert os2.fsSelection & (1 << 7) != 0
    # These are ufo2ft's fallback WinAscent/WinDescent, good enough for now.
    # TODO: Set to the actual global yMin/yMax to prevent any clipping?
    assert os2.usWinAscent == ascender + linegap
    assert os2.usWinDescent == abs(descender)  # always positive


# TODO test that width, height are removed from svg
# TODO test that enable-background is removed from svg
# TODO test that id=glyph# is added to svg
# TODO test svg compressed false, svgz true


@pytest.mark.parametrize(
    #  color_format, output_format
    "svgs, expected_ttx, config_overrides",
    [
        # verify glyf removes component if there is only one shape
        (("one_rect.svg",), "one_rect_glyf.ttx", {"color_format": "glyf"}),
        # simple fill on rect
        (("rect.svg",), "rect_colr_0.ttx", {"color_format": "glyf_colr_0"}),
        (("rect.svg",), "rect_colr_1.ttx", {"color_format": "glyf_colr_1"}),
        (
            ("rect.svg",),
            "rect_picosvg.ttx",
            {"color_format": "picosvg", "pretty_print": True},
        ),
        (("rect.svg",), "rect_untouchedsvg.ttx", {"color_format": "untouchedsvg"}),
        # linear gradient on rect
        (
            ("linear_gradient_rect.svg",),
            "linear_gradient_rect_colr_1.ttx",
            {"color_format": "glyf_colr_1"},
        ),
        # radial gradient on rect
        (
            ("radial_gradient_rect.svg",),
            "radial_gradient_rect_colr_1.ttx",
            {"color_format": "glyf_colr_1"},
        ),
        # reuse shape in different color
        (
            ("rect.svg", "rect2.svg"),
            "rects_colr_1.ttx",
            {"color_format": "glyf_colr_1"},
        ),
        # clocks have composites, reuse of composite, and reuse of shape w/diff color
        (
            ("one-o-clock.svg", "two-o-clock.svg"),
            "clocks_colr_1.ttx",
            {"color_format": "glyf_colr_1"},
        ),
        (
            ("one-o-clock.svg", "two-o-clock.svg"),
            "clocks_glyf.ttx",
            {"color_format": "glyf"},
        ),
        (
            ("one-o-clock.svg", "two-o-clock.svg"),
            "clocks_picosvg.ttx",
            {"color_format": "picosvg", "pretty_print": True},
        ),
        # passing a negative --reuse_tolerance disables shape reuse
        (
            ("one-o-clock.svg", "two-o-clock.svg"),
            "clocks_colr_1_noreuse.ttx",
            {"color_format": "glyf_colr_1", "reuse_tolerance": -1},
        ),
        # clocks share shapes, rects share shapes. Should be two distinct svgs in font.
        # glyph order must reshuffle to group correctly
        (
            ("one-o-clock.svg", "rect.svg", "two-o-clock.svg", "rect2.svg"),
            "clocks_rects_picosvg.ttx",
            {"color_format": "picosvg", "pretty_print": True},
        ),
        (
            ("one-o-clock.svg", "rect.svg", "two-o-clock.svg", "rect2.svg"),
            "clocks_rects_untouchedsvg.ttx",
            {"color_format": "untouchedsvg"},
        ),
        # keep single-component composites if component reused by more than one glyph
        (
            ("one_rect.svg", "one_rect.svg"),
            "reused_rect_glyf.ttx",
            {"color_format": "glyf"},
        ),
        # Confirm transforms are in the correct coordinate space
        # https://github.com/googlefonts/nanoemoji/pull/187
        (
            ("reused_shape.svg",),
            "reused_shape_glyf.ttx",
            {"color_format": "glyf"},
        ),
        # Check gradient coordinates are correctly transformed after shape reuse
        # https://github.com/googlefonts/nanoemoji/issues/334
        (
            ("reused_shape_with_gradient.svg",),
            "reused_shape_with_gradient_colr.ttx",
            {"color_format": "glyf_colr_1", "pretty_print": True},
        ),
        # Check gradient coordinates are correctly transformed after shape reuse
        # https://github.com/googlefonts/nanoemoji/issues/334
        (
            ("reused_shape_with_gradient.svg",),
            "reused_shape_with_gradient_svg.ttx",
            {"color_format": "picosvg", "pretty_print": True},
        ),
        # Confirm we can apply a user transform, override some basic metrics
        (
            ("one_rect.svg",),
            "one_rect_transformed.ttx",
            {
                "color_format": "glyf_colr_1",
                "transform": Affine2D.fromstring(
                    "scale(0.5, 0.75) translate(50) rotate(45)"
                ),
                "width": 120,
            },
        ),
        # Check that we use xlink:href to reuse shapes with <use> elements
        # https://github.com/googlefonts/nanoemoji/issues/266
        (
            ("reused_shape_2.svg",),
            "reused_shape_2_picosvg.ttx",
            {"color_format": "picosvg", "pretty_print": True},
        ),
        # Safari can't deal with gradientTransform where matrix.inverse() == self,
        # we work around it by nudging one matrix component by an invisible amount
        # https://github.com/googlefonts/nanoemoji/issues/268
        (
            ("involutory_matrix.svg",),
            "involutory_matrix_picosvg.ttx",
            {"color_format": "picosvg", "pretty_print": True},
        ),
        # Check that we do _not_ make composite glyphs with reused paths if
        # the latter overlap and the transform for the shape reuse is such
        # that the winding direction is reversed
        # https://github.com/googlefonts/nanoemoji/issues/287
        (
            ("transformed_components_overlap.svg",),
            "transformed_components_overlap.ttx",
            {"color_format": "glyf_colr_1"},
        ),
        # Check we can produce a group with opacity from a Paint graph
        # https://github.com/googlefonts/nanoemoji/issues/315
        (
            ("group_opacity.svg",),
            "group_opacity_picosvg.ttx",
            {"color_format": "picosvg", "pretty_print": True},
        ),
        # Confirm we can reuse elements in a group; was screwing up id generation
        (
            ("group_opacity_reuse.svg",),
            "group_opacity_reuse_picosvg.ttx",
            {"color_format": "picosvg", "pretty_print": True},
        ),
        # https://github.com/googlefonts/nanoemoji/issues/324
        (
            ("transformed_gradient_reuse.svg",),
            "transformed_gradient_reuse.ttx",
            {"color_format": "glyf_colr_1"},
        ),
        # Fill handling in ot-svg reuse
        # https://github.com/googlefonts/nanoemoji/issues/337
        (
            ("reuse_shape_varying_fill.svg",),
            "reuse_shape_varying_fill.ttx",
            {"color_format": "picosvg", "pretty_print": True},
        ),
        # Generate simple cbdt
        (
            ("rect2.svg",),
            "rect_cbdt.ttx",
            # we end up with out of bounds line metrics with default ascender/descender
            {"color_format": "cbdt", "ascender": 90, "descender": -20},
        ),
        # Generate proportional cbdt
        (
            ("rect2.svg", "narrow_rects/a.svg"),
            "proportional_cbdt.ttx",
            # we end up with out of bounds line metrics with default ascender/descender
            # width 0 forces sizing entirely from the input box proportions
            {"color_format": "cbdt", "ascender": 90, "descender": -20, "width": 0},
        ),
        # Generate simple sbix
        (
            ("rect2.svg",),
            "rect_sbix.ttx",
            {"color_format": "sbix"},
        ),
        # The cheeks on the similing face noto-emoji are two identical circles painted
        # with same radial gradients, translated some units apart; check that after we
        # re<use> the same path for both cheeks, their gradients still looks ok.
        # https://github.com/googlefonts/nanoemoji/issues/324
        (
            ("emoji_u263a.svg",),
            "smiley_cheeks_gradient_svg.ttx",
            {"color_format": "picosvg", "pretty_print": True},
        ),
    ],
)
def test_write_font_binary(svgs, expected_ttx, config_overrides):
    config, glyph_inputs = test_helper.color_font_config(config_overrides, svgs)
    _, ttfont = write_font._generate_color_font(config, glyph_inputs)
    ttfont = test_helper.reload_font(ttfont)
    # sanity check the font
    # glyf should not have identical-except-name entries except .notdef and .space
    # SVG should not have identical paths or gradients
    # in both cases this should be true when normalized to start from 0,0
    test_helper.assert_expected_ttx(svgs, ttfont, expected_ttx)


@pytest.mark.parametrize(
    "svgs, config_overrides, expected_clip_boxes",
    [
        (
            ("one_rect.svg",),
            {},
            # original rect's (xMin, yMin, xMax, yMax) with no user-transform
            [(20, 60, 80, 80)],
        ),
        (
            ("one_rect.svg",),
            # rotate 90 degrees clockwise around (20, 60)
            {"transform": Affine2D.fromstring("rotate(-90, 20, 60)")},
            [(20, 0, 40, 60)],
        ),
        (
            ("one_rect.svg",),
            # flatten so that bounds area == 0
            {"transform": Affine2D.fromstring("matrix(0 0 0 1 0 0)")},
            None,
        ),
        (
            # SVG contains no paths, UFO glyph empty: bounds are None
            ("empty.svg",),
            {},
            None,
        ),
        (
            # this SVG contains two triangles flipped vertically around the middle,
            # with each triangle's bbox half-viewbox wide; the union of their bboxes
            # encompasses the full extent of the upem/viewbox.
            # Reflection may play tricks if the bbox doesn't get normalized, cf.
            # https://github.com/googlefonts/nanoemoji/issues/335
            ("flipped_reused_shape.svg",),
            {},
            [(0, 0, 100, 100)],
        ),
        (
            # Check that we correctly compute the bounds of a rectangle that
            # is reused in a following glyph with a 45 degree rotation:
            # https://github.com/googlefonts/nanoemoji/issues/341
            ("rotated_bounds_1.svg", "rotated_bounds_2.svg"),
            {},
            [(10, 10, 90, 90), (22, 22, 78, 78)],
        ),
    ],
)
def test_ufo_color_base_glyph_bounds(svgs, config_overrides, expected_clip_boxes):
    config_overrides = {"output_file": "font.ufo", **config_overrides}
    config, glyph_inputs = test_helper.color_font_config(config_overrides, svgs)
    ufo, _ = write_font._generate_color_font(config, glyph_inputs)

    base_glyph_names = [f"e{str(i).zfill(3)}" for i in range(len(svgs))]
    for base_glyph_name in base_glyph_names:
        assert len(ufo[base_glyph_name]) == 0

    if expected_clip_boxes is not None:
        clip_boxes = ufo.lib[COLR_CLIP_BOXES_KEY]
        assert len(clip_boxes) == len(svgs) == len(expected_clip_boxes)

        for base_glyph_name, (glyphs, bounds), expected_bounds in zip(
            base_glyph_names, clip_boxes, expected_clip_boxes
        ):
            assert glyphs == [base_glyph_name]
            assert bounds == pytest.approx(expected_bounds)
    else:
        assert COLR_CLIP_BOXES_KEY not in ufo.lib


class TestCurrentColor:
    # Chec that we use foreground color palette index 0xFFFF for SVG fill='currentColor'
    # https://github.com/googlefonts/nanoemoji/issues/380
    @staticmethod
    def generate_color_font(svgs, config_overrides):
        config, glyph_inputs = test_helper.color_font_config(config_overrides, svgs)
        _, ttfont = write_font._generate_color_font(config, glyph_inputs)
        return test_helper.reload_font(ttfont)

    @pytest.mark.parametrize(
        "svgs, expected_alpha",
        [
            (("currentColor.svg",), 1.0),
            (("currentColor_with_opacity.svg",), 0.5),
        ],
    )
    def test_colr_1(self, svgs, expected_alpha):
        config_overrides = {"color_format": "glyf_colr_1"}
        ttfont = self.generate_color_font(svgs, config_overrides)
        colr = ttfont["COLR"].table
        assert len(colr.BaseGlyphList.BaseGlyphPaintRecord) == len(svgs)
        color_glyph = colr.BaseGlyphList.BaseGlyphPaintRecord[0]
        assert color_glyph.Paint.Format == ot.PaintFormat.PaintGlyph
        assert color_glyph.Paint.Paint.Format == ot.PaintFormat.PaintSolid
        assert color_glyph.Paint.Paint.PaletteIndex == 0xFFFF
        assert color_glyph.Paint.Paint.Alpha == expected_alpha

        cpal = ttfont["CPAL"]
        assert len(cpal.palettes) == 1
        # Chrome expects non-empty palettes so we always add a dummy color as workaround
        # assert len(cpal.palettes[0]) == 0
        assert len(cpal.palettes[0]) == 1
        assert cpal.palettes[0][0] == (0, 0, 0, 0xFF)

    @pytest.mark.parametrize(
        # COLRv0 can only encode alpha in CPAL's RGBA colors; since the foreground
        # color palette 0xFFFF is not actually in CPAL, we can't encode a transparent
        # fill="currentColor" with COLRv0, so both these input produce the same
        # result, i.e. an opaque foreground color.
        "svgs",
        [("currentColor.svg",), ("currentColor_with_opacity.svg",)],
    )
    def test_colr_0(self, svgs):
        config_overrides = {"color_format": "glyf_colr_0"}
        ttfont = self.generate_color_font(svgs, config_overrides)
        colr = ttfont["COLR"]
        assert len(colr.ColorLayers) == len(svgs)
        glyph_layers = next(iter(colr.ColorLayers.values()))
        assert len(glyph_layers) == 1
        assert glyph_layers[0].colorID == 0xFFFF

        cpal = ttfont["CPAL"]
        assert len(cpal.palettes) == 1
        # Chrome expects non-empty palettes so we always add a dummy color as workaround
        # assert len(cpal.palettes[0]) == 0
        assert len(cpal.palettes[0]) == 1
        assert cpal.palettes[0][0] == (0, 0, 0, 0xFF)

    @pytest.mark.parametrize(
        "svgs, expected_opacity",
        [
            (("currentColor.svg",), 1.0),
            (("currentColor_with_opacity.svg",), 0.5),
        ],
    )
    @pytest.mark.parametrize("color_format", ["picosvg", "untouchedsvg"])
    def test_picosvg(self, color_format, svgs, expected_opacity):
        config_overrides = {"color_format": color_format}
        ttfont = self.generate_color_font(svgs, config_overrides)
        svg_table = ttfont["SVG "]
        assert len(svg_table.docList) == len(svgs)
        svg = SVG.fromstring(svg_table.docList[0][0])
        shapes = svg.shapes()
        assert len(shapes) == 1
        assert shapes[0].fill == "currentColor"
        print(svg.tostring(pretty_print=True))
        assert shapes[0].opacity == expected_opacity


class InputFormat(enum.Flag):
    SVG = enum.auto()
    PNG = enum.auto()


@pytest.mark.parametrize(
    "color_format, expected_input_format",
    [
        ("sbix", InputFormat.PNG),
        ("cbdt", InputFormat.PNG),
        ("glyf_colr_0", InputFormat.SVG),
        ("glyf_colr_1", InputFormat.SVG),
        ("cff_colr_0", InputFormat.SVG),
        ("cff_colr_1", InputFormat.SVG),
        ("cff2_colr_0", InputFormat.SVG),
        ("cff2_colr_1", InputFormat.SVG),
        ("picosvg", InputFormat.SVG),
        ("picosvgz", InputFormat.SVG),
        ("untouchedsvg", InputFormat.SVG),
        ("untouchedsvgz", InputFormat.SVG),
    ],
)
def test_inputs_have_svg_and_or_bitmap(tmp_path, color_format, expected_input_format):
    # Check that inputs have their 'svg' attribute set to a parsed picosvg.SVG object
    # for all the color formats that use that, including 'untouchedsvg'; only bitmap
    # formats don't use that so their InputGlyph.svg attribute is None.
    # https://github.com/googlefonts/nanoemoji/issues/378
    # Also check that inputs have their 'bitmap' attribute set to the PNG bytes for
    # all the color formats that include that.
    expected_has_svgs = bool(expected_input_format & InputFormat.SVG)
    expected_has_bitmaps = bool(expected_input_format & InputFormat.PNG)

    config = _DEFAULT_CONFIG._replace(color_format=color_format)

    assert config.has_svgs is expected_has_svgs
    assert config.has_bitmaps is expected_has_bitmaps

    cp = 0xE001
    glyph_mappings = []
    for i, svg_file in enumerate(("rect.svg", "rect2.svg")):
        svg_file = Path(shutil.copy(test_helper.locate_test_file(svg_file), tmp_path))

        bitmap_file = None
        if expected_input_format & InputFormat.PNG:
            bitmap_file = svg_file.with_suffix(".png")
            test_helper.rasterize_svg(svg_file, bitmap_file, config.bitmap_resolution)

        if not expected_input_format & InputFormat.SVG:
            svg_file = None

        glyph_mappings.append(
            GlyphMapping(svg_file, bitmap_file, (cp + i,), f"uni{i:04X}")
        )

    inputs = list(write_font._inputs(config, glyph_mappings))

    for ginp, gmap in zip(inputs, glyph_mappings):
        assert ginp[:4] == dataclasses.astuple(gmap)
        assert ginp.glyph_name == gmap.glyph_name
        assert ginp.codepoints == gmap.codepoints

    if expected_has_svgs:
        assert all(isinstance(g.svg_file, Path) for g in inputs)
        assert all(isinstance(g.svg, SVG) for g in inputs)
    else:
        assert all(g.svg_file is None for g in inputs)
        assert all(g.svg is None for g in inputs)

    if expected_has_bitmaps:
        assert all(isinstance(g.bitmap_file, Path) for g in inputs)
        assert all(isinstance(g.bitmap, bytes) for g in inputs)
    else:
        assert all(g.bitmap_file is None for g in inputs)
        assert all(g.bitmap is None for g in inputs)


def test_square_varied_hmetrics():
    # square in varied width vbox
    # https://codepen.io/rs42/pen/xxPBrRJ?editors=1100
    svgs = (
        "square_vbox_narrow.svg",
        "square_vbox_square.svg",
        "square_vbox_wide.svg",
    )
    config, glyph_inputs = test_helper.color_font_config({"width": 0}, svgs)
    _, font = write_font._generate_color_font(config, glyph_inputs)

    colr = font["COLR"]

    glyph_names = {r.BaseGlyph for r in colr.table.BaseGlyphList.BaseGlyphPaintRecord}
    assert (
        len(glyph_names) == 3
    ), f"Should have 3 color glyphs, got {names_of_colr_glyphs}"

    glyphs = {p.Glyph for p in paints_of_type(font, ot.PaintFormat.PaintGlyph)}
    assert (
        len(glyphs) == 1
    ), f"Should only be one glyph referenced from COLR, got {glyphs}"

    glyph_widths = sorted(font["hmtx"][gn][0] for gn in glyph_names)
    for i in range(len(glyph_widths) - 1):
        assert (
            glyph_widths[i] * 2 == glyph_widths[i + 1]
        ), f"n+1 should double, fails at {i}; {glyph_widths}"
