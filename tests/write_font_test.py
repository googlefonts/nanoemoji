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


from nanoemoji import write_font
from nanoemoji.config import _DEFAULT_CONFIG
from picosvg.svg_transform import Affine2D
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
        (("rect.svg",), "rect_picosvg.ttx", {"color_format": "picosvg"}),
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
            {"color_format": "picosvg"},
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
            {"color_format": "picosvg"},
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
            {"color_format": "picosvg"},
        ),
        # Safari can't deal with gradientTransform where matrix.inverse() == self,
        # we work around it by nudging one matrix component by an invisible amount
        # https://github.com/googlefonts/nanoemoji/issues/268
        (
            ("involutory_matrix.svg",),
            "involutory_matrix_picosvg.ttx",
            {"color_format": "picosvg"},
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
    "svgs, config_overrides, expected",
    [
        (
            ("one_rect.svg",),
            {},
            # original rect's (xMin, yMin, xMax, yMax) with no user-transform
            (20, 60, 80, 80),
        ),
        (
            ("one_rect.svg",),
            # rotate 90 degrees clockwise around (20, 60)
            {"transform": Affine2D.fromstring("rotate(-90, 20, 60)")},
            (20, 0, 40, 60),
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
    ],
)
def test_ufo_color_base_glyph_bounds(svgs, config_overrides, expected):
    config_overrides = {"output": "ufo", **config_overrides}
    config, glyph_inputs = test_helper.color_font_config(config_overrides, svgs)
    ufo, _ = write_font._generate_color_font(config, glyph_inputs)

    base_glyph = ufo["e000"]
    bounds = base_glyph.getControlBounds(ufo)

    if expected is not None:
        assert bounds == pytest.approx(expected)
        # 1 contour with 2 points
        assert len(base_glyph) == 1
        assert len(base_glyph[0]) == 2
    else:
        assert bounds is None
        assert len(base_glyph) == 0
