# Experimental ninja

from ninja import ninja_syntax
import os

_SRC_DIR = os.path.expanduser('~/oss/color-fonts/font-srcs')
_BUILD_DIR = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '../build'))

def self_dir(path):
    return os.path.dirname(os.path.abspath(__file__))


def rel_self(path):
    self_dir = self_dir()
    path = os.path.normpath(os.path.join(self_dir, path))
    return os.path.relpath(path, self_dir)


def rel_build(path):
    return os.path.relpath(path, _BUILD_DIR)


def resolve_rel_build(path):
    return os.path.abspath(os.path.join(_BUILD_DIR, path))


def rel_src(path):
    return os.path.relpath(path, _SRC_DIR)


def write_rules(nw):
    nw.rule('picosvg', 'picosvg $in > $out || echo "$in failed picosvg"')
    nw.newline()


def find_svgs():
    for root, _, files in os.walk(_SRC_DIR):
        for file in files:
            if not file.endswith('.svg'):
                continue
            yield os.path.join(root, file)


def write_picosvg_builds(nw):
    for svg_file in find_svgs():
        dest_picosvg_file = resolve_rel_build(rel_src(svg_file))
        root, ext = os.path.splitext(dest_picosvg_file)
        dest_picosvg_file = root + '.pico' + ext
        nw.build(rel_build(dest_picosvg_file), 'picosvg', rel_build(svg_file))
    nw.newline()


def main():
    build_file = resolve_rel_build('build.ninja')
    print(f'Writing {build_file}')

    os.makedirs(os.path.dirname(build_file), exist_ok=True)
    with open(build_file, 'w') as f:
        nw = ninja_syntax.Writer(f)

        write_rules(nw)
        write_picosvg_builds(nw)

if __name__ == "__main__":
    main()
