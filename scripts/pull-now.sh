#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
git fetch origin
git pull --ff-only origin main
echo "OK: pulled latest main"
