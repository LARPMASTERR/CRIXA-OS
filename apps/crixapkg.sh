#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

for candidate in \
  "$SCRIPT_DIR/crixapkg.py" \
  "/usr/local/bin/crixapkg.py" \
  "$(pwd)/apps/crixapkg.py"; do
  if [[ -f "$candidate" ]] && command -v python3 >/dev/null 2>&1; then
    exec python3 "$candidate" "$@"
  fi
done

printf 'crixapkg could not locate crixapkg.py or python3.\n' >&2
exit 127
