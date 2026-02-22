#!/usr/bin/env bash
set -euo pipefail

# Tidy up stray SQLite DB files by moving them into the groceries/ folder
# Usage: run from the repository root (the folder that contains this scripts/ dir)

NOW=$(date +%Y%m%dT%H%M%S)
ROOT_DIR=$(pwd)
GROC_DIR="$ROOT_DIR/groceries"

echo "Repository root: $ROOT_DIR"
echo "Target groceries dir: $GROC_DIR"

move_if_exists() {
  src="$1"
  if [ -f "$src" ]; then
    base_name=$(basename "$src")
    dest="$GROC_DIR/$base_name"
    if [ -f "$dest" ]; then
      dest="$GROC_DIR/${base_name}.bak.$NOW"
    fi
    echo "Moving $src -> $dest"
    mv "$src" "$dest"
  else
    echo "Not found: $src"
  fi
}

# Common candidate locations (relative to repo root)
move_if_exists "$ROOT_DIR/groceries.db"
move_if_exists "$ROOT_DIR/../groceries.db"

echo "Done. Current files in $GROC_DIR:"
ls -lah "$GROC_DIR" | sed -n '1,120p'

echo "Note: .gitignore already updated to ignore these DB files. Commit the changes to .gitignore and this script." 
