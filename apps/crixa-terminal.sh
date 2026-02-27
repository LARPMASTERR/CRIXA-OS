#!/usr/bin/env bash
set -Eeuo pipefail

export WINIT_X11_SCALE_FACTOR=1
export ALACRITTY_LOG=error

if command -v systemd-detect-virt >/dev/null 2>&1 && systemd-detect-virt -q; then
  if command -v xterm >/dev/null 2>&1; then
    exec xterm -fa "DejaVu Sans Mono" -fs 10 -bg "#0b1220" -fg "#dbeafe" -title "CRIXA Terminal"
  fi
fi

if command -v alacritty >/dev/null 2>&1; then
  exec alacritty --title "CRIXA Terminal"
fi

if command -v xterm >/dev/null 2>&1; then
  exec xterm -title "CRIXA Terminal"
fi

exit 1
