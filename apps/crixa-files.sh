#!/usr/bin/env bash
set -Eeuo pipefail

if ! command -v thunar >/dev/null 2>&1; then
  exit 1
fi

thunar --daemon >/dev/null 2>&1 || true

if [[ "$#" -gt 0 ]]; then
  exec thunar "$@"
fi

exec thunar
