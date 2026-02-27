#!/usr/bin/env bash
set -Eeuo pipefail

if command -v python3 >/dev/null 2>&1; then
  exec python3 /usr/local/bin/crixa-store.py "$@"
fi

exit 1
