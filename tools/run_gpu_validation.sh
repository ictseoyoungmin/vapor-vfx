#!/bin/sh
# Real native GPU/Hybrid validation. Additional arguments are forwarded unchanged.
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
exec python3 "$ROOT/tools/validate_runtime.py" --build --modes gpu hybrid --capture "$@"
