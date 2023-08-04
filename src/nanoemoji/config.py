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

from absl import flags

try:
    import importlib.resources as resources  # pytype: disable=import-error
except ImportError:
    import importlib_resources as resources  # pytype: disable=import-error

import itertools
from pathlib import Path
from picosvg.svg_transform import Affine2D
import toml
from typing import Any, Iterable, MutableMapping, NamedTuple, Optional, Tuple, Sequence

from nanoemoji import util


FLAGS = flags.FLAGS


_DEFAULT_CONFIG_FILE = "_default.toml"
# NOTE: this must be kept in sync with nanoemoji.write_font._COLOR_FORMAT_GENERATORS
_COLOR_FORMATS = [
    "glyf",
    "glyf_colr_0",
    "glyf_colr_1",
    "cff_colr_0",
    "cff_colr_1",
    "cff2_colr_0",
    "cff2_colr_1",
    "picosvg",
    "picosvgz",
    "untouchedsvg",
    "untouchedsvgz",
    "cbdt",
    "sbix",
]


# we use None as a sentinel for flag not set; FontConfig class has the actual defaults.
# CLI flags override config file (which overrides default FontConfig).
flags.DEFINE_integer("upem", None, "Units per em.")
flags.DEFINE_integer("width", None, "Width.")
flags.DEFINE_integer("ascender", None, "Ascender")
flags.DEFINE_integer("descender", None, "Descender.")
flags.DEFINE_integer("linegap", None, "Line gap.")
flags.DEFINE_string("transform", None, "User transform, in font coordinates.")
flags.DEFINE_integer("version_major", None, "Major version.")
flags.DEFINE_integer("version_minor", None, "Minor version.")
flags.DEFINE_string("family", None, "Family name.")
flags.DEFINE_string("output_file", None, "Output filename.")
flags.DEFINE_enum(
    "color_format",
    None,
    sorted(_COLOR_FORMATS),
    "Type of font to generate.",
)
flags.DEFINE_bool(
    "keep_glyph_names", None, "Whether or not to store glyph names in the font."
)
flags.DEFINE_bool("clip_to_viewbox", None, "Whether to clip content outside viewbox.")
flags.DEFINE_float(
    "reuse_tolerance",
    None,
    "Allowable absolute difference in reused shape in input coordinates (e.g. svg)."
    " Normalized shapes snap to whole multiples of tolerance;"
    " A negative value means that shape reuse is disabled.",
)
# https://github.com/googlefonts/picosvg/issues/138
flags.DEFINE_bool(
    "ignore_reuse_error",
    None,
    "Whether to fail or continue with a warning when picosvg cannot compute "
    "affine between paths that normalize the same.",
)
flags.DEFINE_integer(
    "clipbox_quantization",
    None,
    "Whether to quantize COLR clip boxes to multiples of positive integer, i.e. "
    "rounding {x,y}Min => -Inf (floor) and {x,y}Max => +Inf (ceiling). "
    "By default, it's 2% of UPEM (e.g. multiples of 20 units out of 1024).",
    lower_bound=1,
)
flags.DEFINE_bool(
    "pretty_print",
    None,
    "Whether to prefer pretty printed content whenever possible (for testing).",
)
flags.DEFINE_string("fea_file", None, "Feature file.")
flags.DEFINE_string(
    "glyphmap_generator",
    None,
    "A program that takes a list of filenames and outputs a file csv whose rows contain filename, codepoint(s), glyph name.",
)
flags.DEFINE_integer(
    "bitmap_resolution", None, "Resolution of bitmap in pixels. Always square for now."
)
flags.DEFINE_bool(
    "use_zopflipng", None, "Whether or not to compress PNGs using zopfli."
)
flags.DEFINE_bool(
    "use_pngquant", None, "Whether or not to quantize PNGs using pngquant."
)
flags.DEFINE_string(
    "pngquant_flags", None, "Additional options to pass on to pngquant."
)


class Axis(NamedTuple):
    axisTag: str
    name: str
    default: float


class AxisPosition(NamedTuple):
    axisTag: str
    position: float


class MasterConfig(NamedTuple):
    name: str
    style_name: str
    output_ufo: str
    position: Tuple[AxisPosition, ...]
    sources: Tuple[Path, ...]

    def pos(self, axisTag: str) -> float:
        position = [ap.position for ap in self.position if ap.axisTag == axisTag]
        assert (
            len(position) == 1
        ), f"Unable to find 1 position for {axisTag}, got {position}"
        return position[0]


class FontConfig(NamedTuple):
    family: str = "An Emoji Family"
    output_file: str = "AnEmojiFamily.ttf"
    color_format: str = "glyf_colr_1"
    # metrics default based on Noto Emoji
    upem: int = 1024
    width: int = 1275
    ascender: int = 950
    descender: int = -250
    linegap: int = 0
    transform: Affine2D = Affine2D.identity()
    version_major: int = 1
    version_minor: int = 0
    reuse_tolerance: float = 0.1
    ignore_reuse_error: bool = True
    keep_glyph_names: bool = False
    clip_to_viewbox: bool = True
    clipbox_quantization: Optional[int] = None
    fea_file: str = "features.fea"
    glyphmap_generator: str = "nanoemoji.write_glyphmap"
    bitmap_resolution: int = 128
    use_zopflipng: bool = True
    use_pngquant: bool = True
    # we default to the same PNGQUANTFLAGS used in noto-emoji's Makefile:
    # https://github.com/googlefonts/noto-emoji/blob/9a5261d/Makefile#L24
    pngquant_flags: str = "--speed 1 --skip-if-larger --quality 85-95"
    pretty_print: bool = False
    axes: Tuple[Axis, ...] = ()
    masters: Tuple[MasterConfig, ...] = ()
    source_names: Tuple[str, ...] = ()

    def _has_any(self, *color_formats) -> bool:
        return bool(set(color_formats).intersection(self.color_format.split("_")))

    @property
    def output_format(self):
        return Path(self.output_file).suffix

    @property
    def has_bitmaps(self) -> bool:
        return self._has_any("sbix", "cbdt")

    @property
    def has_picosvgs(self) -> bool:
        return self._has_any("glyf", "colr", "picosvg", "picosvgz")

    @property
    def has_untouchedsvgs(self) -> bool:
        return self._has_any("untouchedsvg", "untouchedsvgz")

    @property
    def has_svgs(self) -> bool:
        return self.has_picosvgs or self.has_untouchedsvgs

    @property
    def is_vf(self) -> bool:
        return len(self.masters) > 1

    @property
    def is_ot_svg(self) -> bool:
        return self._has_any(
            "".join(p)
            for p in itertools.product(("picosvg", "untouchedsvg"), ("", "z"))
        )

    def validate(self):
        for attr_name in (
            "upem",
            "width",
            "ascender",
            "linegap",
            "version_major",
            "version_minor",
        ):
            value = getattr(self, attr_name)
            if value < 0:
                raise ValueError(f"'{attr_name}' must be zero or positive")

        if self.descender > 0:
            raise ValueError("'descender' must be zero or negative")

        if self.clipbox_quantization is not None and self.clipbox_quantization < 1:
            raise ValueError("If set, 'clipbox_quantization' must be 1 or positive")

        # sanity check
        assert self.has_svgs or self.has_bitmaps

        if self.is_vf:
            if self.has_bitmaps:
                raise ValueError("bitmap formats cannot have multiple masters")
            if self.is_ot_svg:
                raise ValueError("OT-SVG formats cannot have multiple masters")

        return self

    def default(self) -> MasterConfig:
        for master in self.masters:
            if all(master.pos(axis.axisTag) == axis.default for axis in self.axes):
                return master
        raise ValueError("Must have a default master")


def write(dest: Path, config: FontConfig):
    toml_cfg = {
        "family": config.family,
        "output_file": config.output_file,
        "color_format": config.color_format,
        "upem": config.upem,
        "width": config.width,
        "ascender": config.ascender,
        "descender": config.descender,
        "linegap": config.linegap,
        "transform": config.transform.tostring(),
        "version_major": config.version_major,
        "version_minor": config.version_minor,
        "reuse_tolerance": config.reuse_tolerance,
        "ignore_reuse_error": config.ignore_reuse_error,
        "keep_glyph_names": config.keep_glyph_names,
        "clip_to_viewbox": config.clip_to_viewbox,
        "clipbox_quantization": config.clipbox_quantization,
        "pretty_print": config.pretty_print,
        "fea_file": config.fea_file,
        "glyphmap_generator": config.glyphmap_generator,
        "bitmap_resolution": config.bitmap_resolution,
        "use_zopflipng": config.use_zopflipng,
        "use_pngquant": config.use_pngquant,
        "pngquant_flags": config.pngquant_flags,
        "axis": {
            a.axisTag: {
                "name": a.name,
                "default": a.default,
            }
            for a in config.axes
        },
        "master": {
            m.name: {
                "style_name": m.style_name,
                "position": {p.axisTag: p.position for p in m.position},
                "srcs": [str(p) for p in m.sources],
            }
            for m in config.masters
        },
    }
    dest.write_text(toml.dumps(toml_cfg))


def _resolve_config(
    config_file: Optional[Path] = None,
) -> Tuple[Optional[Path], MutableMapping[str, Any]]:
    if config_file is None:
        with resources.path("nanoemoji.data", _DEFAULT_CONFIG_FILE) as config_file:
            # no config_dir in this context; bad input if we need it
            return None, toml.load(config_file)
    return config_file.parent, toml.load(config_file)


def _resolve_src(relative_base: Optional[Path], src: str) -> Iterable[Path]:
    src_path = Path(src)
    if src_path.is_absolute():
        if "*" in src:
            root, *stem = src_path.parts
            return tuple(Path(root).glob("/".join(stem)))
        return (src_path,)

    if relative_base is None:
        raise ValueError(f"No relative_base, unable to resolve {src_path}")

    if "*" in src:
        return tuple(relative_base.glob(src))
    return (relative_base.joinpath(src_path),)


_DEFAULT_CONFIG = FontConfig()


def _pop_flag(config: MutableMapping[str, Any], name: str) -> Any:
    config_value = config.pop(name, None)
    flag_value = getattr(FLAGS, name)
    if config_value is None and flag_value is None:
        return getattr(_DEFAULT_CONFIG, name)
    return flag_value if flag_value is not None else config_value


def load(
    config_file: Optional[Path] = None, additional_srcs: Optional[Tuple[Path]] = None
) -> FontConfig:
    config_dir, config = _resolve_config(config_file)

    # CLI flags will take precedence over the config file
    family = _pop_flag(config, "family")
    output_file = _pop_flag(config, "output_file")
    color_format = _pop_flag(config, "color_format")
    upem = int(_pop_flag(config, "upem"))
    width = int(_pop_flag(config, "width"))
    ascender = int(_pop_flag(config, "ascender"))
    descender = int(_pop_flag(config, "descender"))
    linegap = int(_pop_flag(config, "linegap"))
    transform = _pop_flag(config, "transform")
    if not isinstance(transform, Affine2D):
        assert isinstance(transform, str)
        transform = Affine2D.fromstring(transform)
    version_major = int(_pop_flag(config, "version_major"))
    version_minor = int(_pop_flag(config, "version_minor"))
    reuse_tolerance = float(_pop_flag(config, "reuse_tolerance"))
    ignore_reuse_error = _pop_flag(config, "ignore_reuse_error")
    keep_glyph_names = _pop_flag(config, "keep_glyph_names")
    clip_to_viewbox = _pop_flag(config, "clip_to_viewbox")
    clipbox_quantization = _pop_flag(config, "clipbox_quantization")
    pretty_print = _pop_flag(config, "pretty_print")
    fea_file = _pop_flag(config, "fea_file")
    glyphmap_generator = _pop_flag(config, "glyphmap_generator")
    bitmap_resolution = _pop_flag(config, "bitmap_resolution")
    use_zopflipng = _pop_flag(config, "use_zopflipng")
    use_pngquant = _pop_flag(config, "use_pngquant")
    pngquant_flags = _pop_flag(config, "pngquant_flags")

    axes = []
    for axis_tag, axis_config in config.pop("axis").items():
        axes.append(
            Axis(
                axis_tag,
                axis_config.pop("name"),
                axis_config.pop("default"),
            )
        )
        if axis_config:
            raise ValueError(f"Unexpected '{axis_tag}' config: {axis_config}")

    masters = []
    source_names = set()
    for master_name, master_config in config.pop("master").items():
        positions = tuple(
            sorted(AxisPosition(k, v) for k, v in master_config.pop("position").items())
        )
        srcs = set()
        if "srcs" in master_config:
            for src in master_config.pop("srcs"):
                srcs.update(_resolve_src(config_dir, src))
        if additional_srcs is not None:
            srcs.update(additional_srcs)
        srcs = tuple(sorted(util.abspath(p) for p in srcs))

        master = MasterConfig(
            master_name,
            master_config.pop("style_name"),
            ".".join(
                (
                    Path(output_file).stem,
                    master_name,
                    "ufo",
                )
            ),
            positions,
            srcs,
        )
        if master_config:
            raise ValueError(f"Unexpected '{master_name}' config: {master_config}")

        masters.append(master)

        master_source_names = {s.name for s in master.sources}
        if len(master_source_names) != len(master.sources):
            raise ValueError(f"Input svgs for {master_name} must have unique names")
        if not source_names:
            source_names = master_source_names
        elif source_names != master_source_names:
            raise ValueError(f"{fonts[i].name} srcs don't match {fonts[0].name}")

    if not masters:
        raise ValueError("Must have at least one master")
    if config:
        raise ValueError(f"Unexpected config: {config}")

    return FontConfig(
        family=family,
        output_file=output_file,
        color_format=color_format,
        upem=upem,
        width=width,
        ascender=ascender,
        descender=descender,
        linegap=linegap,
        transform=transform,
        version_major=version_major,
        version_minor=version_minor,
        reuse_tolerance=reuse_tolerance,
        ignore_reuse_error=ignore_reuse_error,
        keep_glyph_names=keep_glyph_names,
        clip_to_viewbox=clip_to_viewbox,
        clipbox_quantization=clipbox_quantization,
        pretty_print=pretty_print,
        fea_file=fea_file,
        glyphmap_generator=glyphmap_generator,
        bitmap_resolution=bitmap_resolution,
        use_zopflipng=use_zopflipng,
        use_pngquant=use_pngquant,
        pngquant_flags=pngquant_flags,
        axes=tuple(axes),
        masters=tuple(masters),
        source_names=tuple(sorted(source_names)),
    ).validate()


def load_configs(
    config_files: Sequence[Path], additional_srcs: Optional[Tuple[Path]] = None
) -> Tuple[FontConfig]:
    configs = tuple(load(f, additional_srcs) for f in config_files)
    output_files = {c.output_file for c in configs}
    assert len(configs) == len(
        output_files
    ), f"{len(output_files)} for {len(configs)} configs. Outputs:\n" + "\n".join(
        sorted(output_files)
    )
    return configs
