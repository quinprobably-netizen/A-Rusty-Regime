#!/usr/bin/env bash
# Pull the latest changes, then build and run. Only changed files download and rebuild.
cd "$(dirname "$0")" || exit 1
git pull --ff-only || echo "Could not update, running the version you have."
cargo run --release
