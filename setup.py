"""Just a toy, enough setuptools to be able to install.
"""
from setuptools import setup, find_packages

setup(
    name="nanoemoji",
    version="0.1",
    package_dir={'': 'src'},
    packages=find_packages(where='src'),
    entry_points={
        'console_scripts': [
            'nanoemoji=nanoemoji.nanoemoji:main',
        ],
    },

    install_requires=[
        "absl-py>=0.9.0",
        "lxml>=4.0",
        "skia-pathops>=0.3",
    ],

    # metadata to display on PyPI
    author="Rod S",
    author_email="rsheeter",
    description=(
        "Exploratory utility for COLR fonts"
    ),
)