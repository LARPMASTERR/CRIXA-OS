#!/bin/sh

# First-party launcher for the CRIXA shell.
if command -v crixa-dashboard >/dev/null 2>&1 \
  && command -v python3 >/dev/null 2>&1 \
  && python3 -c 'import PySide2.QtWidgets' >/dev/null 2>&1; then
  if crixa-dashboard "$@"; then
    exit 0
  fi
fi

if command -v krunner >/dev/null 2>&1; then
  exec krunner
fi

if command -v rofi >/dev/null 2>&1; then
  ROFI_THEME="${XDG_CONFIG_HOME:-$HOME/.config}/rofi/config.rasi"
  if [ -f "$ROFI_THEME" ]; then
    exec rofi -show drun -show-icons -no-lazy-grab -theme "$ROFI_THEME"
  fi
  exec rofi -show drun -show-icons -no-lazy-grab
fi

printf 'Orbit could not find crixa-dashboard, krunner, or rofi.\n' >&2
exit 127
