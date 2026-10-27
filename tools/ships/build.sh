#!/usr/bin/env sh
# Build the ship glbs with headless Blender. Needs Python 3.11 for the bpy wheel; shares the weapons' venv.
set -e
cd "$(dirname "$0")"
PY=${PYTHON311:-python3.11}
VENV=../weapons/.venv
[ -d "$VENV" ] || { "$PY" -m venv "$VENV" && "$VENV/bin/pip" install --quiet bpy; }
"$VENV/bin/python" build.py "$@"
