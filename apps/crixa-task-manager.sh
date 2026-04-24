#!/usr/bin/env bash
set -Eeuo pipefail

if command -v systemmonitor >/dev/null 2>&1; then
  exec systemmonitor "$@"
fi

exec python3 /usr/local/bin/crixa-task-manager.py "$@"
