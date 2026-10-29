# Sourced by the build.sh scripts: `run build.py args...` runs a build script in headless Blender.
#
# Uses $BLENDER, else the newest official build unpacked in ~/.local/opt/blender-*/, else `blender`
# on PATH. Official blender.org builds carry the oneAPI Level Zero adapter, so Cycles bakes on Q's
# Arc GPU. With none of those it falls back to the pip bpy wheel in $VENV, which needs Python 3.11
# and only ever bakes on the CPU (the wheel lacks that adapter).

blender_bin() {
    if [ -n "$BLENDER" ]; then echo "$BLENDER"; return; fi
    b=$(ls -d "$HOME"/.local/opt/blender-*/blender 2>/dev/null | sort -V | tail -n 1)
    if [ -n "$b" ]; then echo "$b"; return; fi
    command -v blender || true
}

run() {
    script=$1
    shift
    b=$(blender_bin)
    if [ -n "$b" ]; then
        exec "$b" -b --factory-startup -noaudio --python-exit-code 1 --python "$script" -- "$@"
    fi
    PY=${PYTHON311:-python3.11}
    [ -d "$VENV" ] || { "$PY" -m venv "$VENV" && "$VENV/bin/pip" install --quiet bpy; }
    exec "$VENV/bin/python" -u "$script" "$@"
}
