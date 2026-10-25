@echo off
rem Pull the latest changes, then build and run. Only changed files download and rebuild.
rem An optional map: play.bat system (solar system), moon, arena; nothing is the island.
cd /d "%~dp0"
rem --autostash sets your own edits (tuning.toml and the like) aside, updates, then puts them back.
git pull --ff-only --autostash
if errorlevel 1 (
    echo.
    echo COULD NOT UPDATE: you are about to play the OLD version. Run "git status" to see why.
    pause
)
if not "%~1"=="" set RUST_REGIME_LEVEL=%~1
cargo run --release
pause
