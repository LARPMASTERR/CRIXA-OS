#!/usr/bin/env bash
set -Eeuo pipefail

export XDG_CURRENT_DESKTOP="CRIXA-Wayland"
export XDG_SESSION_DESKTOP="crixa-wayland"
export XDG_SESSION_TYPE="wayland"
export MOZ_ENABLE_WAYLAND=1
export QT_QPA_PLATFORM=wayland
export QT_AUTO_SCREEN_SCALE_FACTOR=1

if [[ -f "$HOME/.config/labwc/environment" ]]; then
  # shellcheck source=/dev/null
  . "$HOME/.config/labwc/environment"
fi

if command -v labwc >/dev/null 2>&1; then
  if command -v dbus-run-session >/dev/null 2>&1; then
    exec dbus-run-session labwc
  fi
  exec labwc
fi

if command -v dbus-run-session >/dev/null 2>&1; then
  exec dbus-run-session weston --xwayland
fi

exec weston --xwayland
