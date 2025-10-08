scripts\push-merge-main.cmd ci-fix-egl-full
``]

## 3) (Raspberry) `scripts/pull-now.sh`
_Einfaches Update-Helperscript auf dem Pi._

```sh
#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
git fetch origin
git pull --ff-only origin main
echo "OK: pulled latest main"
