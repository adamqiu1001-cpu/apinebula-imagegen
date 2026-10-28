#!/bin/sh
set -eu
APINEBULA_REPO=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$APINEBULA_REPO"
[ "$(uname -s)" = Darwin ] || { echo 'Please build the Mac package on macOS.' >&2; exit 1; }
APINEBULA_BOOTSTRAP=${APINEBULA_BUILD_PYTHON:-python3}
"$APINEBULA_BOOTSTRAP" -c 'import sys; assert sys.version_info[:2] == (3,13), "Maintainers need Python 3.13 to build"'
"$APINEBULA_BOOTSTRAP" -m venv .build/venv
.build/venv/bin/python -B packaging/prepare.py macos
.build/venv/bin/python -B packaging/build_packages.py macos
