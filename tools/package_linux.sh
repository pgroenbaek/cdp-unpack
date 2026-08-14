#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
DIST_DIR="$ROOT_DIR/dist"

PYTHON="${PYTHON:-python3}"

cd "$ROOT_DIR"

echo "==> Cleaning dist/"
rm -rf "$DIST_DIR"
mkdir -p "$DIST_DIR"

echo "==> Building wheel + source distribution"
"$PYTHON" -m build --wheel --sdist --outdir "$DIST_DIR"

echo "==> Building Nuitka executable"
"$PYTHON" -m nuitka \
    --onefile \
    --python-flag=-m \
    --output-dir="$DIST_DIR" \
    --output-filename=cdpunpack \
    "$ROOT_DIR/cdpunpack"

echo
echo "==> Build complete:"
ls -lh "$DIST_DIR"