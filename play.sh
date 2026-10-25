#!/usr/bin/env bash
# Pull the latest changes, then build and run. Only changed files download and rebuild.
cd "$(dirname "$0")" || exit 1
# --autostash sets your own edits (tuning.toml and the like) aside, updates, then puts them back.
if ! git pull --ff-only --autostash; then
    echo
    echo "COULD NOT UPDATE: you are about to play the OLD version. Run 'git status' to see why."
    read -rp "Press Enter to play the old version anyway, or Ctrl+C to stop. "
fi
cargo run --release
