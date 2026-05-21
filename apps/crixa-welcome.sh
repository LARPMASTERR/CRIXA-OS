#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

for candidate in \
  "$SCRIPT_DIR/crixa-welcome.py" \
  "/usr/local/bin/crixa-welcome.py" \
  "$(pwd)/apps/crixa-welcome.py"; do
  if [[ -f "$candidate" ]] && command -v python3 >/dev/null 2>&1; then
    exec python3 "$candidate" "$@"
  fi
done

printf 'CRIXA Welcome could not locate crixa-welcome.py or python3.\n' >&2
exit 127
