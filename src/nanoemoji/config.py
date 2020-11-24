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
from pathlib import Path
import toml
from typing import NamedTuple, Tuple, Sequence


FLAGS = flags.FLAGS


flags.DEFINE_string(
    "config", str(Path(__file__).parent / "default.toml"), "Config file"
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


class FontConfig(NamedTuple):
    family: str = "An Emoji Family"
    output_file: str = "AnEmojiFamily.ttf"
    color_format: str = "glyf_colr_1"
    upem: int = 1024
    reuse_tolerance: float = 0.1
    keep_glyph_names: bool = False
    output: str = "font"
    fea_file: str = "features.fea"
    codepointmap_file: str = "codepointmap.csv"
    axes: Tuple[Axis, ...] = ()
    masters: Tuple[MasterConfig, ...] = ()
    source_names: Tuple[str, ...] = ()

    @property
    def output_format(self):
        return Path(self.output_file).suffix


def write(dest: Path, config: FontConfig):
    toml_cfg = {
        "family": config.family,
        "output_file": config.output_file,
        "color_format": config.color_format,
        "upem": config.upem,
        "reuse_tolerance": config.reuse_tolerance,
        "keep_glyph_names": config.keep_glyph_names,
        "output": config.output,
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


def load(config_file: Path = None, additional_srcs: Tuple[Path] = None) -> FontConfig:
    if config_file is None:
        config_file = Path(FLAGS.config).resolve()

    default_config = FontConfig()

    config = toml.load(config_file)
    config_dir = config_file.parent

    family = config.pop("family", default_config.family)
    output_file = config.pop("output_file", default_config.output_file)
    color_format = config.pop("color_format", default_config.color_format)
    upem = int(config.pop("upem", default_config.upem))
    reuse_tolerance = float(
        config.pop("reuse_tolerance", default_config.reuse_tolerance)
    )
    keep_glyph_names = config.pop("keep_glyph_names", default_config.keep_glyph_names)
    output = config.pop("output", default_config.output)

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
                if Path(src).is_file():
                    srcs.add(Path(src))
                else:
                    srcs |= set(config_dir.glob(src))
        if additional_srcs is not None:
            srcs |= set(additional_srcs)
        srcs = tuple(sorted(srcs))

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
        family,
        output_file,
        color_format,
        upem,
        reuse_tolerance,
        keep_glyph_names,
        output,
        default_config.fea_file,
        default_config.codepointmap_file,
        tuple(axes),
        tuple(masters),
        tuple(sorted(source_names)),
    )
