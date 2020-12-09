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
import pytest
import test_helper


@pytest.mark.parametrize(
    "svgs", [("rect.svg", "rect2.svg"), ("one-o-clock.svg", "two-o-clock.svg")]
)
@pytest.mark.parametrize(
    "color_format", ["glyf_colr_0", "glyf_colr_1", "picosvg", "untouchedsvg"]
)
@pytest.mark.parametrize("keep_glyph_names", [True, False])
@pytest.mark.usefixtures("absl_flags")
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
    ],
)
@pytest.mark.usefixtures("absl_flags")
def test_write_font_binary(svgs, expected_ttx, config_overrides):
    config, glyph_inputs = test_helper.color_font_config(config_overrides, svgs)
    _, ttfont = write_font._generate_color_font(config, glyph_inputs)
    ttfont = test_helper.reload_font(ttfont)
    # sanity check the font
    # glyf should not have identical-except-name entries except .notdef and .space
    # SVG should not have identical paths or gradients
    # in both cases this should be true when normalized to start from 0,0
    test_helper.assert_expected_ttx(svgs, ttfont, expected_ttx)
