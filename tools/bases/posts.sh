#!/usr/bin/env sh
# Build the post glbs (small scattered faction outposts) with headless Blender (which one: ../blender.sh).
set -e
cd "$(dirname "$0")"
VENV=../weapons/.venv
. ../blender.sh
run posts.py "$@"
