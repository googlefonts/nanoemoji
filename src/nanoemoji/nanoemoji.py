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
nanoemoji -v 1 $(find ~/oss/noto-emoji/svg -name '*.svg')
nanoemoji $(find ~/oss/twemoji/assets/svg -name '*.svg')
"""
from absl import app
from absl import flags
from absl import logging
import glob
from nanoemoji import codepoints, config, write_font
from nanoemoji.config import AxisPosition, FontConfig, MasterConfig
from nanoemoji.util import fs_root, rel, only
from ninja import ninja_syntax
import os
from pathlib import Path
import re
import subprocess
import sys
from typing import List, NamedTuple, Optional, Tuple, Set, Sequence


FLAGS = flags.FLAGS


# internal flags, typically client wouldn't change
flags.DEFINE_string("build_dir", "build/", "Where build runs.")
flags.DEFINE_bool("gen_ninja", True, "Whether to regenerate build.ninja")
flags.DEFINE_bool(
    "gen_svg_font_diffs", False, "Whether to generate svg vs font render diffs."
)
flags.DEFINE_integer("svg_font_diff_resolution", 256, "Render diffs resolution")
flags.DEFINE_bool("exec_ninja", True, "Whether to run ninja.")


def self_dir() -> Path:
    return Path(__file__).parent.resolve()


def build_dir() -> Path:
    return Path(FLAGS.build_dir).resolve()


def rel_self(path: Path) -> Path:
    return rel(self_dir(), path)


def rel_build(path: Path) -> Path:
    return rel(build_dir(), path)


def _get_bool_flag(name: str):
    return getattr(FLAGS, name)


def _bool_flag(name: str, value: bool):
    flag = " --"
    if not value:
        flag += "no"
    flag += name
    return flag


def _per_config_file(font_config: FontConfig, suffix: str) -> Path:
    return build_dir() / Path(font_config.output_file).with_suffix(suffix).name


def _config_file(font_config: FontConfig) -> Path:
    return _per_config_file(font_config, ".toml")


def _source_name_file(font_config: FontConfig) -> Path:
    return _per_config_file(font_config, ".source_names.txt")


def _fea_file(font_config: FontConfig) -> Path:
    return _per_config_file(font_config, ".fea")


def _font_rule(font_config: FontConfig) -> str:
    suffix = "_font"
    if _is_vf(font_config):
        suffix = "_vfont"
    return Path(font_config.output_file).stem + suffix


def _ufo_rule(font_config: FontConfig, master: MasterConfig) -> str:
    return (
        "write_"
        + Path(font_config.output_file).stem
        + "_"
        + master.style_name.lower()
        + "_ufo"
    )


def _ufo_config(font_config: FontConfig, master: MasterConfig) -> Path:
    return _per_config_file(font_config, "." + master.output_ufo + ".toml")


def _glyphmap_rule(font_config: FontConfig, master: MasterConfig) -> str:
    master_part = ""
    if _is_vf(font_config):
        master_part = "_" + master.style_name.lower()
    return "write_" + Path(font_config.output_file).stem + master_part + "_glyphmap"


def _glyphmap_file(font_config: FontConfig, master: MasterConfig) -> Path:
    master_part = ""
    if _is_vf(font_config):
        master_part = "." + master.output_ufo
    return _per_config_file(font_config, master_part + ".glyphmap")


def module_rule(
    nw,
    mod_name,
    arg_pattern,
    rspfile=None,
    rspfile_content=None,
    rule_name=None,
    allow_external=False,
):
    if not rule_name:
        rule_name = mod_name
    if not allow_external:
        mod_name = "nanoemoji." + mod_name
    nw.rule(
        rule_name,
        f"{sys.executable} -m {mod_name} -v {FLAGS.verbosity} {arg_pattern}",
        rspfile=rspfile,
        rspfile_content=rspfile_content,
    )


def write_font_rule(nw, font_config: FontConfig, master: MasterConfig):
    if _is_vf(font_config):
        rule_name = _ufo_rule(font_config, master)
        config_file = _ufo_config(font_config, master)
    else:
        rule_name = _font_rule(font_config)
        config_file = _config_file(font_config)

    module_rule(
        nw,
        "write_font",
        " ".join(
            (
                f"--config_file {rel_build(config_file)}",
                f"--fea_file {rel_build(_fea_file(font_config))}",
                f"--glyphmap_file {rel_build(_glyphmap_file(font_config, master))}",
                "@$out.rsp",
            )
        ),
        rspfile="$out.rsp",
        rspfile_content="$in",
        rule_name=rule_name,
    )
    nw.newline()


def write_glyphmap_rule(nw, font_config: FontConfig, master: MasterConfig):
    module_rule(
        nw,
        font_config.glyphmap_generator,
        f"--output_file $out $in",
        rspfile="$out.rsp",
        rspfile_content="$in",
        rule_name=_glyphmap_rule(font_config, master),
        allow_external=True,
    )
    nw.newline()


def write_preamble(nw):
    nw.comment("Generated by nanoemoji")
    nw.newline()

    nw.rule(
        f"picosvg_unclipped",
        f"picosvg "
        + _bool_flag("clip_to_viewbox", False)
        + " --output_file $out"
        + " $in",
    )
    nw.newline()

    nw.rule(
        f"picosvg_clipped",
        f"picosvg "
        + _bool_flag("clip_to_viewbox", True)
        + " --output_file $out"
        + " $in",
    )
    nw.newline()

    module_rule(nw, "write_fea", "--output_file $out $in")
    nw.newline()


def write_config_preamble(nw, font_config: FontConfig):
    for master in font_config.masters:
        write_font_rule(nw, font_config, master)
    if _is_vf(font_config):
        module_rule(
            nw,
            "write_variable_font",
            f"--config_file {_config_file(font_config)} $in",
            rule_name=_font_rule(font_config),
        )

    if FLAGS.gen_svg_font_diffs:
        nw.rule(
            "write_svg2png",
            f"resvg -h {FLAGS.svg_font_diff_resolution}  -w {FLAGS.svg_font_diff_resolution} $in $out",
        )
        module_rule(
            nw,
            "write_font2png",
            f"--height {FLAGS.svg_font_diff_resolution}  --width {FLAGS.svg_font_diff_resolution} --output_file $out $in",
        )
        module_rule(nw, "write_pngdiff", f"--output_file $out $in")
        module_rule(
            nw,
            "write_diffreport",
            f"--lhs_dir resvg_png --rhs_dir skia_png --output_file $out @$out.rsp",
            rspfile="$out.rsp",
            rspfile_content="$in",
        )
        nw.newline()

    nw.newline()


def picosvg_dir(master_name: str) -> Path:
    return build_dir() / "picosvg" / master_name


def picosvg_dest(master_name: str, clipped: bool, input_svg: Path) -> str:
    out_dir = picosvg_dir(master_name)
    if clipped:
        out_dir = out_dir / "clipped"
    return str(rel_build(out_dir / input_svg.name))


def resvg_png_dest(input_svg: Path) -> str:
    dest_file = input_svg.stem + ".png"
    return os.path.join("resvg_png", dest_file)


def skia_png_dest(input_svg: Path) -> str:
    dest_file = input_svg.stem + ".png"
    return os.path.join("skia_png", dest_file)


def diff_png_dest(input_svg: Path) -> str:
    dest_file = input_svg.stem + ".png"
    return os.path.join("diff_png", dest_file)


def write_picosvg_builds(
    picosvg_builds: Set[str],
    nw: ninja_syntax.Writer,
    clipped: bool,
    master: MasterConfig,
):
    rule_name = "picosvg_unclipped"
    if clipped:
        rule_name = "picosvg_clipped"
    os.makedirs(str(picosvg_dir(master.name)), exist_ok=True)
    for svg_file in master.sources:
        dest = picosvg_dest(master.name, clipped, svg_file)
        if dest in picosvg_builds:
            continue
        picosvg_builds.add(dest)
        nw.build(dest, rule_name, str(rel_build(svg_file)))


def write_source_names(font_config: FontConfig):
    with open(os.path.join(build_dir(), _source_name_file(font_config)), "w") as f:
        for source_name in font_config.source_names:
            f.write(source_name)
            f.write("\n")


def write_fea_build(nw: ninja_syntax.Writer, font_config: FontConfig):

    nw.build(
        str(rel_build(_fea_file(font_config))),
        "write_fea",
        str(rel_build(_glyphmap_file(font_config, font_config.default()))),
    )
    nw.newline()


def write_svg_font_diff_build(
    nw: ninja_syntax.Writer, font_dest: str, svg_files: Sequence[Path]
):
    # render each svg => png
    for svg_file in svg_files:
        nw.build(resvg_png_dest(svg_file), "write_svg2png", str(rel_build(svg_file)))
    nw.newline()

    # render each input from the font => png
    for svg_file in svg_files:
        inputs = [
            font_dest,
            str(rel_build(svg_file)),
        ]
        nw.build(skia_png_dest(svg_file), "write_font2png", inputs)
    nw.newline()

    # create comparison images
    for svg_file in svg_files:
        inputs = [
            resvg_png_dest(svg_file),
            skia_png_dest(svg_file),
        ]
        nw.build(diff_png_dest(svg_file), "write_pngdiff", inputs)
    nw.newline()

    # write report and kerplode if there are bad diffs
    nw.build("diffs.html", "write_diffreport", [diff_png_dest(f) for f in svg_files])


def _input_svgs(font_config: FontConfig, master: MasterConfig) -> List[str]:
    if font_config.has_picosvgs:
        svg_files = [
            picosvg_dest(master.name, font_config.clip_to_viewbox, f)
            for f in master.sources
        ]
    else:
        svg_files = [str(f.resolve()) for f in master.sources]
    return svg_files


def _update_sources(font_config: FontConfig) -> FontConfig:
    if not font_config.has_picosvgs:
        return font_config
    return font_config._replace(
        masters=tuple(
            master._replace(
                sources=tuple(
                    Path(picosvg_dest(master.name, font_config.clip_to_viewbox, s))
                    for s in master.sources
                )
            )
            for master in font_config.masters
        )
    )


def write_glyphmap_build(
    nw: ninja_syntax.Writer,
    font_config: FontConfig,
    master: MasterConfig,
):
    nw.build(
        str(rel_build(_glyphmap_file(font_config, master))),
        _glyphmap_rule(font_config, master),
        _input_svgs(font_config, master),
    )
    nw.newline()


def _inputs_to_font_build(font_config: FontConfig, master: MasterConfig) -> List[str]:
    return [
        str(rel_build(_config_file(font_config))),
        str(rel_build(_fea_file(font_config))),
        str(rel_build(_glyphmap_file(font_config, master))),
    ] + _input_svgs(font_config, master)


def write_ufo_build(
    nw: ninja_syntax.Writer, font_config: FontConfig, master: MasterConfig
):
    ufo_config = font_config._replace(output_file=master.output_ufo, masters=(master,))
    ufo_config = _update_sources(ufo_config)
    config.write(build_dir() / _ufo_config(font_config, master), ufo_config)
    nw.build(
        master.output_ufo,
        _ufo_rule(font_config, master),
        _inputs_to_font_build(font_config, master),
    )
    nw.newline()


def write_static_font_build(nw: ninja_syntax.Writer, font_config: FontConfig):
    assert len(font_config.masters) == 1
    nw.build(
        font_config.output_file,
        _font_rule(font_config),
        _inputs_to_font_build(font_config, font_config.default()),
    )
    nw.newline()


def write_variable_font_build(nw: ninja_syntax.Writer, font_config: FontConfig):
    nw.build(
        font_config.output_file,
        _font_rule(font_config),
        [str(rel_build(_fea_file(font_config)))]
        + [m.output_ufo for m in font_config.masters],
    )
    nw.newline()


def _write_config_for_build(font_config: FontConfig):
    # Dump config with defaults, CLI args, etc resolved to build
    # and sources updated to point to build picosvgs
    font_config = _update_sources(font_config)
    config_file = _config_file(font_config)
    config.write(config_file, font_config)
    logging.info(f"Wrote {config_file.relative_to(build_dir().parent)}")


def _is_vf(font_config: FontConfig) -> bool:
    return len(font_config.masters) > 1


def _is_svg(font_config: FontConfig) -> bool:
    return font_config.color_format.endswith(
        "svg"
    ) or font_config.color_format.endswith("svgz")


def _run(argv):
    additional_srcs = tuple(Path(f) for f in argv if f.endswith(".svg"))
    font_configs = config.load_configs(
        tuple(Path(f) for f in argv if f.endswith(".toml")),
        additional_srcs=additional_srcs,
    )
    if not font_configs:
        font_configs = (config.load(additional_srcs=additional_srcs),)

    os.makedirs(build_dir(), exist_ok=True)
    if FLAGS.gen_svg_font_diffs:
        os.makedirs(os.path.join(build_dir(), "resvg_png"), exist_ok=True)
        os.makedirs(os.path.join(build_dir(), "skia_png"), exist_ok=True)
        os.makedirs(os.path.join(build_dir(), "diff_png"), exist_ok=True)
    build_file = build_dir() / "build.ninja"

    assert not FLAGS.gen_svg_font_diffs or (
        len(font_configs) == 1
    ), "Can only generate diffs for one font at a time"

    if len(font_configs) > 1:
        assert all(not _is_vf(c) for c in font_configs)

    logging.info(f"Proceeding with {len(font_configs)} config(s)")

    for font_config in font_configs:
        if _is_vf(font_config) and _is_svg(font_config):
            raise ValueError("svg formats cannot have multiple masters")
        _write_config_for_build(font_config)
        write_source_names(font_config)

    if FLAGS.gen_ninja:
        logging.info(f"Generating {build_file.relative_to(build_dir())}")
        with open(build_file, "w") as f:
            nw = ninja_syntax.Writer(f)
            write_preamble(nw)

            # Separate loops for separate content to keep related rules together

            for font_config in font_configs:
                for master in font_config.masters:
                    write_glyphmap_rule(nw, font_config, master)

            for font_config in font_configs:
                write_config_preamble(nw, font_config)

            for font_config in font_configs:
                write_fea_build(nw, font_config)

            for font_config in font_configs:
                for master in font_config.masters:
                    write_glyphmap_build(nw, font_config, master)

            picosvg_builds = set()
            for font_config in font_configs:
                for master in font_config.masters:
                    if not font_config.color_format.startswith("untouchedsvg"):
                        write_picosvg_builds(
                            picosvg_builds, nw, font_config.clip_to_viewbox, master
                        )
            nw.newline()

            for font_config in font_configs:
                if FLAGS.gen_svg_font_diffs:
                    assert not _is_vf(font_config)
                    write_svg_font_diff_build(
                        nw, font_config.output_file, font_config.masters[0].sources
                    )

                for master in font_config.masters:
                    if _is_vf(font_config):
                        write_ufo_build(nw, font_config, master)

            for font_config in font_configs:
                if _is_vf(font_config):
                    write_variable_font_build(nw, font_config)
                else:
                    write_static_font_build(nw, font_config)

    ninja_cmd = ["ninja", "-C", os.path.dirname(build_file)]
    if FLAGS.exec_ninja:
        logging.info(" ".join(ninja_cmd))
        subprocess.run(ninja_cmd, check=True)
    else:
        logging.info("To run: " + " ".join(ninja_cmd))


def main():
    # We don't seem to be __main__ when run as cli tool installed by setuptools
    app.run(_run)


if __name__ == "__main__":
    app.run(_run)
