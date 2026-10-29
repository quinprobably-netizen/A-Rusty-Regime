#!/usr/bin/env sh
# Build the first-person weapon glbs with headless Blender (which one: ../blender.sh).
set -e
cd "$(dirname "$0")"
VENV=.venv
. ../blender.sh
run build.py "$@"
