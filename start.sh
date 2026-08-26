#!/bin/bash
# Thin wrapper — all logic is in launcher.py
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
exec python3 "$SCRIPT_DIR/launcher.py" "$@"
