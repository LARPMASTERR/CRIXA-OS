#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

for candidate in \
  "$SCRIPT_DIR/crixa-store.py" \
  "/usr/local/bin/crixa-store.py" \
  "$(pwd)/apps/crixa-store.py"; do
  if [[ -f "$candidate" ]] && command -v python3 >/dev/null 2>&1; then
    exec python3 "$candidate" "$@"
  fi
done

printf 'Foundry could not locate crixa-store.py or python3.\n' >&2
exit 127
