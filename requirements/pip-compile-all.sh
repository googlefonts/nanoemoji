#!/bin/bash
# Runs pip-compile to freeze requirements.txt for all supported pythons
# that are listed in the tox.ini default envlist.
# It is recommended to run this every time any top-level requirements in either
# install-requirements.in or dev-requirements.in are added, removed or changed.
# The script must be run from the same directory where tox.ini file is located,
# and it requires that all the supported python3.X binaries are installed
# locally and available on $PATH.
# It also requires that the venv module is present in all of them, in order to
# create the temporary virtual environment where to install pip-compile.
# On most python distributions venv is part of the standard library, however on
# some Linux distros (e.g. Debian) it needs to be installed separately.

set -e

TMPDIR="$(mktemp -d)"

function compile_requirements {
    local python_cmd=${1}
    echo "Updating ${python_cmd}-requirements.txt"

    "${python_cmd}" -m venv "${TMPDIR}/${python_cmd}-venv"

    local venv_bin="${TMPDIR}/${python_cmd}-venv/bin"
    local pip_cmd="${venv_bin}/pip"
    "${pip_cmd}" install -qq pip-tools

    local pip_compile_cmd="${venv_bin}/pip-compile"
    "${pip_compile_cmd}" -q --upgrade \
        -o requirements/${python_cmd}-requirements.txt \
        requirements/install-requirements.in \
        requirements/dev-requirements.in
}

[ -f "tox.ini" ] || { echo "ERROR: tox.ini file not found" ; exit 1; }

running=false
# `tox -l` prints all the environments listed in the tox.ini's default 'envlist'
for toxenv in $(tox -l); do
    if [[ $toxenv =~ py([0-9])([0-9]+) ]]; then
        version_major=${BASH_REMATCH[1]}
        version_minor=${BASH_REMATCH[2]}
        compile_requirements "python${version_major}.${version_minor}" &
        running=true
    fi
done

if $running; then
    sleep 0.5
    echo "Please wait while all the requirements files are updated..."
    wait
    echo "Done!"
fi

# clean up after us before leaving
rm -r "${TMPDIR}"
