"""Just a toy, enough setuptools to be able to install.
"""
from setuptools import setup, find_packages

setup(
    name="nanoemoji",
    version="0.1",
    package_dir={"": "src"},
    packages=find_packages(where="src"),
    entry_points={"console_scripts": ["nanoemoji=nanoemoji.nanoemoji:main",],},
    install_requires=[
        "absl-py>=0.9.0",
        "CairoSVG>=2.4.2",
        "fs==2.4.11",
        "lxml>=4.0",
        "nanosvg>=0.1",
        "regex>=2020.4.4",
        "skia-pathops>=0.3",
        "ufo2ft>=2.13.0",
        "ufoLib2>=0.6.2",
        # Horrible horrors lie here. Remove after merges.
        "fontTools @ https://github.com/fonttools/fonttools/tarball/otdata-colr",
    ],
    # metadata to display on PyPI
    author="Rod S",
    author_email="rsheeter@google.com",
    description=("Exploratory utility for color fonts"),
)
