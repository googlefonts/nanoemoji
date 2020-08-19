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

setup(
    name="nanoemoji",
    use_scm_version={"write_to": "src/nanoemoji/_version.py"},
    package_dir={"": "src"},
    packages=find_packages(where="src"),
    entry_points={"console_scripts": ["nanoemoji=nanoemoji.nanoemoji:main"]},
    setup_requires=["setuptools_scm"],
    install_requires=[
        "absl-py>=0.9.0",
        "fonttools[ufo]>=4.13.0",
        "lxml>=4.0",
        "ninja>=1.10.0.post1",
        "picosvg>=0.6.1",
        "pillow>=7.2.0",
        "regex>=2020.4.4",
        "ufo2ft[cffsubr]>=2.15.0",
        "ufoLib2>=0.6.2",
        "dataclasses>=0.7; python_version < '3.7'",
    ],
    python_requires=">=3.6",
    # metadata to display on PyPI
    author="Rod S",
    author_email="rsheeter@google.com",
    description=("Exploratory compiler for color fonts"),
)
