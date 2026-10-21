@echo off
rem Pull the latest changes, then build and run. Only changed files download and rebuild.
cd /d "%~dp0"
git pull --ff-only || echo Could not update, running the version you have.
cargo run --release
pause
