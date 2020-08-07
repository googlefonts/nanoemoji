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


flags.DEFINE_string("config", None, "Config file")


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
    position: Tuple[AxisPosition]
    sources: Tuple[Path]


class FontConfig(NamedTuple):
    output_file: str
    color_format: str
    axes: Tuple[Axis]
    masters: Tuple[MasterConfig]
    source_names: Tuple[str]


def _consume(config, key):
    return config.pop(key)


def load(config_file: Path = None) -> FontConfig:
    if config_file is None:
        config_file = Path(FLAGS.config).resolve()

    config = toml.load(config_file)
    config_dir = config_file.parent
    output_file = _consume(config, "output_file")
    color_format = _consume(config, "color_format")

    axes = []
    for axis_tag, axis_config in _consume(config, "axis").items():
        axes.append(
            Axis(
                axis_tag,
                _consume(axis_config, "name"),
                _consume(axis_config, "default"),
            )
        )
        if axis_config:
            raise ValueError(f"Unexpected '{axis_tag}' config: {axis_config}")

    masters = []
    source_names = set()
    for master_name, master_config in _consume(config, "master").items():
        positions = tuple(
            sorted(
                AxisPosition(k, v)
                for k, v in _consume(master_config, "position").items()
            )
        )
        master = MasterConfig(
            master_name,
            _consume(master_config, "style_name"),
            ".".join((Path(output_file).stem, master_name, "ufo",)),
            positions,
            tuple(config_dir.glob(_consume(master_config, "srcs"))),
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
        output_file,
        color_format,
        tuple(axes),
        tuple(masters),
        tuple(sorted(source_names)),
    )
