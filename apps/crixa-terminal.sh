#!/usr/bin/env bash
set -Eeuo pipefail

export WINIT_X11_SCALE_FACTOR=1
export ALACRITTY_LOG=error

if command -v konsole >/dev/null 2>&1; then
  exec konsole "$@"
fi

if command -v alacritty >/dev/null 2>&1; then
  exec alacritty --title "Console"
fi

if command -v xterm >/dev/null 2>&1; then
  exec xterm -title "Console"
fi

exit 1
