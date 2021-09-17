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

extras_require={
    "test": [
        "pytest",
    ],
    "lint": [
        "black",
        "pytype",
    ],
}
extras_require["dev"] = extras_require["test"] + extras_require["lint"]

setup(
    name="nanoemoji",
    use_scm_version={"write_to": "src/nanoemoji/_version.py"},
    package_dir={"": "src"},
    packages=find_packages(where="src"),
    entry_points={"console_scripts": ["nanoemoji=nanoemoji.nanoemoji:main"]},
    setup_requires=["setuptools_scm"],
    include_package_data=True,
    install_requires=[
        "absl-py>=0.9.0",
        "fonttools[ufo]>=4.26.0",
        "importlib_resources>=3.3.0; python_version < '3.9'",
        "lxml>=4.0",
        "ninja>=1.10.0.post1",
        "picosvg>=0.18.2",
        "pillow>=7.2.0",
        "regex>=2020.4.4",
        "toml>=0.10.1",
        "ufo2ft[cffsubr]>=2.24.0",
        "ufoLib2>=0.6.2",
    ],
    extras_require=extras_require,
    # this is so we can use the built-in dataclasses module
    python_requires=">=3.7",

    # this is for type checker to use our inline type hints:
    # https://www.python.org/dev/peps/pep-0561/#id18
    package_data={"picosvg": ["py.typed"]},

    # metadata to display on PyPI
    author="Rod S",
    author_email="rsheeter@google.com",
    description=("Compiler for color fonts"),
)
