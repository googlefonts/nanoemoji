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
from collections.abc import Iterable
import functools
import glob
from nanoemoji import codepoints, config, write_font
from nanoemoji.config import AxisPosition, FontConfig, MasterConfig
from nanoemoji.ninja import (
    build_dir,
    gen_ninja,
    maybe_run_ninja,
    module_rule,
    rel_build,
    NinjaWriter,
)
from nanoemoji.util import fs_root, rel, only, abspath
import os
from pathlib import Path
import platform
import re
import shlex
import shutil
import subprocess
import sys
from typing import (
    Any,
    Callable,
    List,
    Mapping,
    MutableMapping,
    NamedTuple,
    Optional,
    Tuple,
    Set,
    Sequence,
)


FLAGS = flags.FLAGS


flags.DEFINE_bool(
    "gen_svg_font_diffs", False, "Whether to generate svg vs font render diffs."
)
flags.DEFINE_integer("svg_font_diff_resolution", 256, "Render diffs resolution")


def self_dir() -> Path:
    return Path(__file__).parent.resolve()


def rel_self(path: Path) -> Path:
    return rel(self_dir(), path)


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


def _fea_file(font_config: FontConfig) -> Path:
    return _per_config_file(font_config, ".fea")


def _ufo_config(font_config: FontConfig, master: MasterConfig) -> Path:
    return _per_config_file(font_config, "." + master.output_ufo + ".toml")


def _glyphmap_rule(font_config: FontConfig) -> str:
    return font_config.glyphmap_generator


def _glyphmap_file(font_config: FontConfig, master: MasterConfig) -> Path:
    master_part = ""
    if font_config.is_vf:
        master_part = "." + master.output_ufo
    return _per_config_file(font_config, master_part + ".glyphmap")


def _glyphmap_file(font_config: FontConfig, master: MasterConfig) -> Path:
    master_part = ""
    if font_config.is_vf:
        master_part = "." + master.output_ufo
    return _per_config_file(font_config, master_part + ".glyphmap")


def write_glyphmap_rule(nw, glyphmap_generator):
    module_rule(
        nw,
        glyphmap_generator,
        f"--output_file $out @$out.rsp",
        rspfile="$out.rsp",
        rspfile_content="$in",
        allow_external=True,
    )
    nw.newline()


@functools.lru_cache()
def _chrome_command() -> str:
    cmd, validator = {
        "Linux": ("google-chrome", shutil.which),
        "Darwin": (
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            lambda s: Path(s).is_file(),
        ),
        "Windows": ("chrome", shutil.which),
    }[platform.system()]

    if not validator(cmd):
        raise ValueError(f"Chrome ({cmd}) not found")

    return shlex.quote(cmd)


def write_preamble(nw):
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

    # set height only, let width scale proportionally
    nw.rule(
        "write_bitmap",
        f"resvg -h $res $in $out",
    )
    nw.newline()

    # -y is to always overwrite existing output without Y/N interactive prompt
    zopfli_verbose = ""
    if FLAGS.verbosity:
        zopfli_verbose = "-v"
    nw.rule(
        "zopflipng",
        f"{sys.executable} -m zopfli.png {zopfli_verbose} -y $in $out",
    )
    nw.newline()

    # always overwrite using --force
    pngquant_verbose = ""
    if FLAGS.verbosity:
        pngquant_verbose = "-v"
    module_rule(
        nw, "pngquant", f"-i $in -o $out -- -f {pngquant_verbose} $pngquant_flags"
    )
    nw.newline()

    module_rule(
        nw,
        "write_font",
        f"--config_file $config_file --fea_file $fea_file --glyphmap_file $glyphmap_file $in",
    )

    module_rule(
        nw,
        "write_variable_font",
        f"--config_file $config_file $in",
    )

    if FLAGS.gen_svg_font_diffs:
        res = FLAGS.svg_font_diff_resolution
        chrome_screenshot = " ".join(
            (
                _chrome_command(),
                "--headless",
                f"--window-size=$res,$res",
                "--force-device-scale-factor=1",
                "--virtual-time-budget=1000",
                "--enable-features=COLRV1Fonts",  # unnecessary for 98+
                "--screenshot=$out",
                "$in",
            )
        )
        nw.rule("screenshot", chrome_screenshot)
        nw.rule("copy_font_to_screenshot_dir", "cp $in $out")
        module_rule(
            nw, "write_font2png_html", f"--resolution $res --output_file $out $in"
        )
        module_rule(nw, "write_pngdiff", f"--output_file $out $in")
        module_rule(
            nw,
            "write_diffreport",
            f"--lhs_dir {rel_build(svg2png_dir())} "
            f"--rhs_dir {rel_build(font2png_dir())} "
            "--output_file $out @$out.rsp",
            rspfile="$out.rsp",
            rspfile_content="$in",
        )
        nw.newline()

    nw.newline()


def picosvg_dir() -> Path:
    return build_dir() / "picosvg"


def bitmap_dir() -> Path:
    return build_dir() / "bitmap"


def zopflipng_dir() -> Path:
    return build_dir() / "zopflipng"


def pngquant_dir() -> Path:
    return build_dir() / "pngquant"


def svg2png_dir() -> Path:
    return build_dir() / "imagediff" / "svg2png"


def font2png_dir() -> Path:
    return build_dir() / "imagediff" / "font2png"


def diff_bitmap_dir() -> Path:
    return build_dir() / "imagediff" / "diff"


def _dest_for_src(scope_fn, out_dir: Path, input_svg: Path, suffix: str) -> Path:
    if not hasattr(scope_fn, "names_seen"):
        scope_fn.names_seen = {}
    names_seen = scope_fn.names_seen

    # If  many different inputs have the same name disambiguate 1..N
    # by including N in picosvg path
    input_svg = abspath(input_svg)
    nth_of_name = 0
    while names_seen.get((nth_of_name, input_svg.name), input_svg) != input_svg:
        nth_of_name += 1
    names_seen[(nth_of_name, input_svg.name)] = input_svg

    if nth_of_name > 0:
        out_dir = out_dir / str(nth_of_name)
    return rel_build(out_dir / input_svg.name).with_suffix(suffix)


def picosvg_dest(clipped: bool, input_svg: Path) -> Path:
    out_dir = picosvg_dir()
    if clipped:
        out_dir = out_dir / "clipped"
    return _dest_for_src(picosvg_dest, out_dir, input_svg, ".svg")


def bitmap_dest(input_svg: Path) -> Path:
    return _dest_for_src(bitmap_dest, bitmap_dir(), input_svg, ".png")


def zopflipng_dest(input_svg: Path) -> Path:
    return _dest_for_src(zopflipng_dest, zopflipng_dir(), input_svg, ".png")


def pngquant_dest(input_svg: Path) -> Path:
    return _dest_for_src(pngquant_dest, pngquant_dir(), input_svg, ".png")


def svg2png_dest(input_svg: Path) -> Path:
    return _dest_for_src(svg2png_dest, svg2png_dir(), input_svg, ".png")


def font2png_html_dest(input_svg: Path) -> Path:
    return _dest_for_src(font2png_html_dest, font2png_dir(), input_svg, ".html")


def font2png_dest(input_svg: Path) -> Path:
    return _dest_for_src(font2png_dest, font2png_dir(), input_svg, ".png")


def diff_png_dest(input_svg: Path) -> Path:
    return _dest_for_src(diff_png_dest, diff_bitmap_dir(), input_svg, ".png")


def write_picosvg_builds(
    picosvg_builds: Set[Path],
    nw: NinjaWriter,
    clipped: bool,
    master: MasterConfig,
):
    rule_name = "picosvg_unclipped"
    if clipped:
        rule_name = "picosvg_clipped"
    for svg_file in master.sources:
        svg_file = abspath(svg_file)
        dest = picosvg_dest(clipped, svg_file)
        if svg_file in picosvg_builds:
            continue
        picosvg_builds.add(svg_file)
        nw.build(dest, rule_name, rel_build(svg_file))


def write_bitmap_builds(
    bitmap_builds: Set[Path],
    nw: NinjaWriter,
    clipped: bool,
    resolution: int,
    master: MasterConfig,
):
    os.makedirs(str(bitmap_dir()), exist_ok=True)
    for svg_file in master.sources:
        dest = bitmap_dest(svg_file)
        if dest in bitmap_builds:
            continue
        bitmap_builds.add(dest)
        nw.build(
            dest, "write_bitmap", rel_build(svg_file), variables={"res": resolution}
        )


def write_compressed_bitmap_builds(
    builds: Set[Path],
    nw: NinjaWriter,
    master: MasterConfig,
    rule_name: str,
    dest_dir: Path,
    infile_fn: Callable[[Path], Path],
    outfile_fn: Callable[[Path], Path],
    variables: Optional[Mapping[str, Any]] = None,
):
    if variables is None:
        variables = {}

    os.makedirs(str(dest_dir), exist_ok=True)
    for svg_file in master.sources:
        dest = outfile_fn(svg_file)
        if dest in builds:
            continue
        builds.add(dest)
        nw.build(dest, rule_name, infile_fn(svg_file), variables=variables)


def write_fea_build(nw: NinjaWriter, font_config: FontConfig):

    nw.build(
        rel_build(_fea_file(font_config)),
        "write_fea",
        rel_build(_glyphmap_file(font_config, font_config.default())),
    )
    nw.newline()


def write_svg_font_diff_build(
    nw: NinjaWriter, font_dest: str, svg_files: Sequence[Path], resolution: int
):
    # render each svg => png
    for svg_file in svg_files:
        nw.build(
            svg2png_dest(svg_file),
            "screenshot",
            rel_build(svg_file),
            variables={"res": resolution},
        )
    nw.newline()

    # copy the output font to the screenshot directory
    font_for_screenshots = font2png_dir() / "Font.ttf"
    nw.build(font_for_screenshots, "copy_font_to_screenshot_dir", font_dest)

    # make an html container for each input in the font
    for svg_file in svg_files:
        inputs = [
            font_for_screenshots,
            rel_build(svg_file),
        ]
        nw.build(
            font2png_html_dest(svg_file),
            "write_font2png_html",
            inputs,
            variables={"res": resolution},
        )
    nw.newline()

    # render the html container => png
    for svg_file in svg_files:
        nw.build(font2png_dest(svg_file), "screenshot", font2png_html_dest(svg_file))
    nw.newline()

    # create comparison images
    for svg_file in svg_files:
        inputs = [
            svg2png_dest(svg_file),
            font2png_dest(svg_file),
        ]
        nw.build(diff_png_dest(svg_file), "write_pngdiff", inputs)
    nw.newline()

    # write report and kerplode if there are bad diffs
    nw.build("diffs.html", "write_diffreport", [diff_png_dest(f) for f in svg_files])


def _input_files(font_config: FontConfig, master: MasterConfig) -> List[Path]:
    input_files = []
    if font_config.has_picosvgs:
        input_files.extend(
            picosvg_dest(font_config.clip_to_viewbox, f) for f in master.sources
        )
    if font_config.has_untouchedsvgs:
        input_files.extend(rel_build(f) for f in master.sources)
    if font_config.has_bitmaps:
        dest_func = bitmap_dest
        if font_config.use_zopflipng:
            dest_func = zopflipng_dest
        elif font_config.use_pngquant:
            dest_func = pngquant_dest
        # zopflipng always happens after pngquant, so when both are true
        # the final desired file is zopflipng_dest
        input_files.extend(dest_func(f) for f in master.sources)
    return input_files


def _update_sources(font_config: FontConfig) -> FontConfig:
    if not font_config.has_picosvgs:
        return font_config
    return font_config._replace(
        masters=tuple(
            master._replace(
                sources=tuple(
                    Path(picosvg_dest(font_config.clip_to_viewbox, s))
                    for s in master.sources
                )
            )
            for master in font_config.masters
        )
    )


def write_glyphmap_build(
    nw: NinjaWriter,
    font_config: FontConfig,
    master: MasterConfig,
):
    nw.build(
        rel_build(_glyphmap_file(font_config, master)),
        _glyphmap_rule(font_config),
        _input_files(font_config, master),
    )
    nw.newline()


def _variables_for_font_build(
    font_config: FontConfig, master: MasterConfig, config_file: Path
) -> MutableMapping[str, Any]:
    return {
        "config_file": rel_build(config_file),
        "fea_file": rel_build(_fea_file(font_config)),
        "glyphmap_file": rel_build(_glyphmap_file(font_config, master)),
    }


def write_ufo_build(nw: NinjaWriter, font_config: FontConfig, master: MasterConfig):
    ufo_config = font_config._replace(output_file=master.output_ufo, masters=(master,))
    ufo_config = _update_sources(ufo_config)
    ufo_config_file = _ufo_config(font_config, master)
    config.write(build_dir() / ufo_config_file, ufo_config)
    variables = _variables_for_font_build(font_config, master, ufo_config_file)
    variables["config_file"] = rel_build(ufo_config_file)
    nw.build(
        master.output_ufo,
        "write_font",
        implicit=list(variables.values()),
        variables=variables,
    )
    nw.newline()


def write_static_font_build(nw: NinjaWriter, font_config: FontConfig):
    assert len(font_config.masters) == 1
    variables = _variables_for_font_build(
        font_config, font_config.default(), _config_file(font_config)
    )
    nw.build(
        font_config.output_file,
        "write_font",
        implicit=list(variables.values()),
        variables=variables,
    )
    nw.newline()


def write_variable_font_build(nw: NinjaWriter, font_config: FontConfig):
    nw.build(
        font_config.output_file,
        "write_variable_font",
        implicit=[rel_build(_fea_file(font_config))]
        + [m.output_ufo for m in font_config.masters],
        variables={"config_file": rel_build(_config_file(font_config))},
    )
    nw.newline()


def _write_config_for_build(font_config: FontConfig):
    # Dump config with defaults, CLI args, etc resolved to build
    # and sources updated to point to build picosvgs
    font_config = _update_sources(font_config)
    config_file = _config_file(font_config)
    config.write(config_file, font_config)
    logging.info(f"Wrote {config_file.relative_to(build_dir().parent)}")


def _run(argv):
    additional_srcs = tuple(Path(f) for f in argv if f.endswith(".svg"))
    font_configs = config.load_configs(
        tuple(Path(f) for f in argv if f.endswith(".toml")),
        additional_srcs=additional_srcs,
    )
    if not font_configs:
        font_configs = (config.load(additional_srcs=additional_srcs),)

    if any(fc.has_bitmaps for fc in font_configs) and not shutil.which("resvg"):
        raise RuntimeError(
            "'resvg' command-line tool not found on $PATH. "
            "Try `pip install resvg-cli` or visit https://github.com/RazrFalcon/resvg."
        )

    required_dirs = [build_dir()]
    if FLAGS.gen_svg_font_diffs:
        required_dirs += [
            svg2png_dir(),
            font2png_dir(),
            diff_bitmap_dir(),
            picosvg_dir(),
        ]
    for required_dir in required_dirs:
        required_dir.mkdir(parents=True, exist_ok=True)
    build_file = build_dir() / "build.ninja"

    assert not FLAGS.gen_svg_font_diffs or (
        len(font_configs) == 1
    ), "Can only generate diffs for one font at a time"

    if len(font_configs) > 1:
        assert all(not c.is_vf for c in font_configs)

    logging.info(f"Proceeding with {len(font_configs)} config(s)")

    for font_config in font_configs:
        _write_config_for_build(font_config)

    if gen_ninja():
        logging.info(f"Generating {build_file.relative_to(build_dir())}")
        with open(build_file, "w") as f:
            nw = NinjaWriter(f)
            write_preamble(nw)

            for glyphmap_generator in sorted(
                {fc.glyphmap_generator for fc in font_configs}
            ):
                write_glyphmap_rule(nw, glyphmap_generator)

            # After rules, builds

            for font_config in font_configs:
                write_fea_build(nw, font_config)

            for font_config in font_configs:
                for master in font_config.masters:
                    write_glyphmap_build(nw, font_config, master)

            picosvg_builds = set()
            for font_config in font_configs:
                for master in font_config.masters:
                    if font_config.has_picosvgs:
                        write_picosvg_builds(
                            picosvg_builds, nw, font_config.clip_to_viewbox, master
                        )
            nw.newline()

            bitmap_builds = set()
            for font_config in font_configs:
                if font_config.has_bitmaps:
                    assert not font_config.is_vf
                    write_bitmap_builds(
                        bitmap_builds,
                        nw,
                        font_config.clip_to_viewbox,  # currently unused
                        font_config.bitmap_resolution,
                        font_config.masters[0],
                    )
            nw.newline()

            zopflipng_builds = set()
            pngquant_builds = set()
            for font_config in font_configs:
                if not font_config.has_bitmaps or not (
                    font_config.use_zopflipng or font_config.use_pngquant
                ):
                    continue
                assert not font_config.is_vf

                master = font_config.masters[0]
                if font_config.use_pngquant:
                    write_compressed_bitmap_builds(
                        pngquant_builds,
                        nw,
                        master,
                        rule_name="pngquant",
                        dest_dir=pngquant_dir(),
                        infile_fn=bitmap_dest,
                        outfile_fn=pngquant_dest,
                        variables={"pngquant_flags": font_config.pngquant_flags},
                    )

                if font_config.use_zopflipng:
                    zopflipng_infile_fn = bitmap_dest
                    if font_config.use_pngquant:
                        zopflipng_infile_fn = pngquant_dest
                        nw.newline()
                    write_compressed_bitmap_builds(
                        zopflipng_builds,
                        nw,
                        master,
                        rule_name="zopflipng",
                        dest_dir=zopflipng_dir(),
                        infile_fn=zopflipng_infile_fn,
                        outfile_fn=zopflipng_dest,
                    )
            nw.newline()

            for font_config in font_configs:
                if FLAGS.gen_svg_font_diffs:
                    assert not font_config.is_vf
                    write_svg_font_diff_build(
                        nw,
                        font_config.output_file,
                        font_config.masters[0].sources,
                        font_config.bitmap_resolution,
                    )

                for master in font_config.masters:
                    if font_config.is_vf:
                        write_ufo_build(nw, font_config, master)

            for font_config in font_configs:
                if font_config.is_vf:
                    write_variable_font_build(nw, font_config)
                else:
                    write_static_font_build(nw, font_config)

    maybe_run_ninja(build_file)


def main():
    # We don't seem to be __main__ when run as cli tool installed by setuptools
    app.run(_run)


if __name__ == "__main__":
    app.run(_run)
