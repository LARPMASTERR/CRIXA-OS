#!/usr/bin/env bash
set -Eeuo pipefail

MODE="${1:-full}"
STAMP="$(date +%Y%m%d-%H%M%S)"
OUT_DIR="${XDG_PICTURES_DIR:-$HOME/Pictures}/Screenshots"
OUT_FILE="$OUT_DIR/crixa-screenshot-$STAMP.png"

notify() {
  local title="$1"
  local body="$2"
  if command -v notify-send >/dev/null 2>&1; then
    notify-send "$title" "$body" >/dev/null 2>&1 || true
  fi
}

copy_to_clipboard() {
  if [[ -n "${WAYLAND_DISPLAY:-}" ]] && command -v wl-copy >/dev/null 2>&1; then
    wl-copy < "$OUT_FILE"
    return 0
  fi
  if [[ -n "${DISPLAY:-}" ]] && command -v xclip >/dev/null 2>&1; then
    xclip -selection clipboard -t image/png -i "$OUT_FILE"
    return 0
  fi
  return 1
}

capture_x11() {
  if command -v maim >/dev/null 2>&1; then
    if [[ "$MODE" == "select" ]]; then
      maim -s "$OUT_FILE" && return 0
    else
      maim "$OUT_FILE" && return 0
    fi
  fi

  if command -v scrot >/dev/null 2>&1; then
    if [[ "$MODE" == "select" ]]; then
      scrot -s -z "$OUT_FILE" && return 0
    else
      scrot -z "$OUT_FILE" && return 0
    fi
  fi

  return 1
}

capture_wayland() {
  if ! command -v grim >/dev/null 2>&1; then
    return 1
  fi

  if [[ "$MODE" == "select" ]] && command -v slurp >/dev/null 2>&1; then
    local region
    region="$(slurp 2>/dev/null || true)"
    [[ -z "$region" ]] && return 1
    grim -g "$region" "$OUT_FILE" && return 0
  else
    grim "$OUT_FILE" && return 0
  fi

  return 1
}

mkdir -p "$OUT_DIR"

if [[ -n "${WAYLAND_DISPLAY:-}" ]]; then
  if ! capture_wayland; then
    notify "CRIXA Screenshot" "No Wayland screenshot backend available."
    exit 1
  fi
else
  if ! capture_x11; then
    notify "CRIXA Screenshot" "Install maim or scrot to capture screenshots."
    exit 1
  fi
fi

if [[ ! -s "$OUT_FILE" ]]; then
  notify "CRIXA Screenshot" "Capture failed."
  exit 1
fi

if copy_to_clipboard; then
  notify "CRIXA Screenshot" "Copied to clipboard and saved to $OUT_FILE"
else
  notify "CRIXA Screenshot" "Saved to $OUT_FILE (clipboard backend missing)"
fi

printf '%s\n' "$OUT_FILE"
