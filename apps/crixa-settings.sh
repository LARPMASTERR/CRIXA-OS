#!/usr/bin/env bash
set -Eeuo pipefail

if command -v systemsettings >/dev/null 2>&1; then
  exec systemsettings "$@"
fi

if command -v python3 >/dev/null 2>&1 && python3 -c "import tkinter" >/dev/null 2>&1; then
  exec python3 /usr/local/bin/crixa-settings.py "$@"
fi

if command -v rofi >/dev/null 2>&1; then
  choice="$(printf '%s\n' "Open Files Config" "Restart Session" "Exit" | rofi -dmenu -i -p "Bridge")"
  case "$choice" in
    "Open Files Config") exec crixa-files "${XDG_CONFIG_HOME:-$HOME/.config}" ;;
    "Restart Session")
      if command -v qdbus >/dev/null 2>&1; then
        exec qdbus org.kde.Shutdown /Shutdown logout
      fi
      exit 0
      ;;
    *) exit 0 ;;
  esac
fi

if command -v notify-send >/dev/null 2>&1; then
  notify-send "Bridge" "Tkinter runtime is missing. Install python3-tk." >/dev/null 2>&1 || true
fi

exit 1
