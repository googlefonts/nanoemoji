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

from setuptools import setup, find_packages
import os.path


def readlines(filename):
    # Return a file's list of lines excluding # comments
    lines = []
    with open(filename, "r") as fp:
        for line in fp:
            line, _, _ = line.partition("#")
            line = line.strip()
            if not line:
                continue
            lines.append(line)
    return lines


# Store top-level depedencies in external requirements.in files, so that
# pip-compile can use them to compile requirements.txt files with full
# dependency graph exploded and all versions pinned (for reproducible tests).
# pip-compile support for setup.py is quite limited: it ignores extras_require,
# as well as environment markers from install_requires:
# https://github.com/jazzband/pip-tools/issues/625
# https://github.com/jazzband/pip-tools/issues/908
# https://github.com/jazzband/pip-tools/issues/1139
install_deps = readlines(os.path.join("requirements", "install-requirements.in"))
develop_deps = readlines(os.path.join("requirements", "dev-requirements.in"))


setup(
    name="nanoemoji",
    use_scm_version={"write_to": "src/nanoemoji/_version.py"},
    package_dir={"": "src"},
    packages=find_packages(where="src"),
    entry_points={"console_scripts": ["nanoemoji=nanoemoji.nanoemoji:main"]},
    setup_requires=["setuptools_scm"],
    include_package_data=True,
    install_requires=install_deps,
    extras_require={
        "dev": develop_deps,
    },
    python_requires=">=3.6",

    # this is for type checker to use our inline type hints:
    # https://www.python.org/dev/peps/pep-0561/#id18
    package_data={"picosvg": ["py.typed"]},

    # metadata to display on PyPI
    author="Rod S",
    author_email="rsheeter@google.com",
    description=("Compiler for color fonts"),
)
