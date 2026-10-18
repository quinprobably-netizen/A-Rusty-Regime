#!/usr/bin/env sh
# Build the character glbs (and preview renders) with headless Blender. Needs Python 3.11 for the bpy wheel.
set -e
cd "$(dirname "$0")"
PY=${PYTHON311:-python3.11}
[ -d .venv ] || { "$PY" -m venv .venv && .venv/bin/pip install --quiet bpy; }
.venv/bin/python build.py "$@"
