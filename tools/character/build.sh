#!/usr/bin/env sh
# Build the character glbs (and preview renders) with headless Blender (which one: ../blender.sh).
#
# The realistic layer (real.py) builds bodies from Blender Studio's Human Base Meshes (CC0); the bundle
# is fetched once into vendor/ (gitignored) when missing.
set -e
cd "$(dirname "$0")"
VENV=.venv
. ../blender.sh
HBM=vendor/human-base-meshes-bundle-v1.4.1
if [ ! -f "$HBM/human_base_meshes_bundle.blend" ]; then
    mkdir -p vendor
    # blender.org's own link answers with an HTML "thanks" page; the mirror serves the zip itself.
    curl -fL --retry 3 -o vendor/hbm.zip https://mirror.blender.org/demo/asset-bundles/human-base-meshes/human-base-meshes-bundle-v1.4.1.zip
    (cd vendor && unzip -q -o hbm.zip && rm hbm.zip)
    [ -f "$HBM/human_base_meshes_bundle.blend" ] || { echo "unexpected layout in the Human Base Meshes zip" >&2; exit 1; }
fi
run build.py "$@"
