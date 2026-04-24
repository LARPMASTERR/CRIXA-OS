#!/usr/bin/env bash
set -Eeuo pipefail

if command -v dolphin >/dev/null 2>&1; then
  if [[ "$#" -gt 0 ]]; then
    exec dolphin "$@"
  fi
  exec dolphin
fi

if command -v thunar >/dev/null 2>&1; then
  thunar --daemon >/dev/null 2>&1 || true
  if [[ "$#" -gt 0 ]]; then
    exec thunar "$@"
  fi
  exec thunar
fi

exit 1
