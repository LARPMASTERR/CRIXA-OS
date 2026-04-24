#!/bin/sh

# First-party launcher for the CRIXA shell.
if command -v crixa-dashboard >/dev/null 2>&1; then
  exec crixa-dashboard
fi

if command -v krunner >/dev/null 2>&1; then
  exec krunner
fi

exec rofi -show drun -show-icons -no-lazy-grab -theme "$HOME/.config/rofi/config.rasi"
