#!/usr/bin/env bash
set -Eeuo pipefail

CONFIG_HOME="${XDG_CONFIG_HOME:-$HOME/.config}"
STATE_DIR="$CONFIG_HOME/crixa-shell"
MARKER="$STATE_DIR/bootstrap-v3.done"
LOOK_AND_FEEL="org.crixa.shell.desktop"
WALLPAPER="/usr/share/backgrounds/crixa/00-defaultwp.jpg"

mkdir -p "$STATE_DIR"

if [[ -f "$MARKER" ]]; then
  exit 0
fi

if command -v plasma-apply-lookandfeel >/dev/null 2>&1; then
  plasma-apply-lookandfeel --apply "$LOOK_AND_FEEL" --resetLayout >/dev/null 2>&1 || true
fi

if command -v crixa-wallpaper >/dev/null 2>&1 && [[ -f "$WALLPAPER" ]]; then
  for _ in 1 2 3 4 5; do
    if pgrep -x plasmashell >/dev/null 2>&1; then
      break
    fi
    sleep 1
  done
  crixa-wallpaper set "$WALLPAPER" >/dev/null 2>&1 || true
fi

if command -v qdbus >/dev/null 2>&1; then
  qdbus org.kde.plasmashell /PlasmaShell org.kde.PlasmaShell.reloadConfig >/dev/null 2>&1 || true
elif command -v qdbus6 >/dev/null 2>&1; then
  qdbus6 org.kde.plasmashell /PlasmaShell org.kde.PlasmaShell.reloadConfig >/dev/null 2>&1 || true
fi

date -Is > "$MARKER"
