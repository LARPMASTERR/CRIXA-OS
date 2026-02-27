#!/usr/bin/env bash
set -Eeuo pipefail

exec python3 /usr/local/bin/crixapkg.py "$@"
