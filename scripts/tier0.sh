#!/usr/bin/env bash
# Run every Tier 0 sweep. See scripts/tier0.py for what each one checks.
# Usage: scripts/tier0.sh [--json]
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
python3 scripts/tier0.py "$@"
