#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [[ "${1:-}" == "--kde-systemmonitor" ]]; then
  shift
  for candidate in systemmonitor plasma-systemmonitor; do
    if command -v "$candidate" >/dev/null 2>&1; then
      exec "$candidate" "$@"
    fi
  done
  printf 'KDE System Monitor is not installed.\n' >&2
  exit 127
fi

for candidate in \
  "$SCRIPT_DIR/crixa-task-manager.py" \
  "/usr/local/bin/crixa-task-manager.py" \
  "$(pwd)/apps/crixa-task-manager.py"; do
  if [[ -f "$candidate" ]] && command -v python3 >/dev/null 2>&1; then
    exec python3 "$candidate" "$@"
  fi
done

printf 'Pulse could not locate crixa-task-manager.py or python3.\n' >&2
exit 127
