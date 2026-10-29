#!/usr/bin/env sh
# Build the ship glbs with headless Blender (which one: ../blender.sh); shares the weapons' venv fallback.
set -e
cd "$(dirname "$0")"
VENV=../weapons/.venv
. ../blender.sh
run build.py "$@"
