#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FRONTEND_DIR="$ROOT_DIR/frontend"
DIST_DIR="$FRONTEND_DIR/dist"

mkdir -p "$DIST_DIR"

cd "$FRONTEND_DIR"
tsc --project tsconfig.json
cp "$FRONTEND_DIR/src/index.html" "$DIST_DIR/index.html"
cp "$FRONTEND_DIR/src/style.css" "$DIST_DIR/style.css"
