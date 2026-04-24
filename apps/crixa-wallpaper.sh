#!/usr/bin/env bash
set -Eeuo pipefail

CONFIG_HOME="${XDG_CONFIG_HOME:-$HOME/.config}"
STATE_DIR="$CONFIG_HOME/crixa"
STATE_FILE="$STATE_DIR/wallpaper.current"
WALL_DIR="/usr/share/backgrounds/crixa"
FALLBACK="/usr/share/backgrounds/crixa/00-defaultwp.jpg"

usage() {
  cat <<'EOF'
Usage:
  crixa-wallpaper apply-current
  crixa-wallpaper set <image-path>
  crixa-wallpaper next
  crixa-wallpaper prev
  crixa-wallpaper random
  crixa-wallpaper list
  crixa-wallpaper status
EOF
}

load_wallpapers() {
  if [[ -d "$WALL_DIR" ]]; then
    mapfile -t WALLPAPERS < <(
      find "$WALL_DIR" -maxdepth 1 -type f \
        \( -iname '*.jpg' -o -iname '*.jpeg' -o -iname '*.png' -o -iname '*.webp' -o -iname '*.bmp' -o -iname '*.svg' \) \
        | sort
    )
  else
    WALLPAPERS=()
  fi
}

current_wallpaper() {
  local current=""
  if [[ -f "$STATE_FILE" ]]; then
    current="$(cat "$STATE_FILE")"
  fi
  if [[ -n "$current" && -f "$current" ]]; then
    printf '%s\n' "$current"
    return 0
  fi
  if [[ -f "$FALLBACK" ]]; then
    printf '%s\n' "$FALLBACK"
    return 0
  fi
  if [[ "${#WALLPAPERS[@]}" -gt 0 ]]; then
    printf '%s\n' "${WALLPAPERS[0]}"
    return 0
  fi
  return 1
}

apply_wallpaper() {
  local target="$1"
  local qdbus_bin=""
  local target_uri=""
  local script=""

  target="$(readlink -f "$target")"
  mkdir -p "$STATE_DIR"
  printf '%s\n' "$target" > "$STATE_FILE"

  if command -v plasma-apply-wallpaperimage >/dev/null 2>&1; then
    plasma-apply-wallpaperimage "$target" >/dev/null 2>&1 || true
  fi

  if command -v qdbus >/dev/null 2>&1; then
    qdbus_bin="qdbus"
  elif command -v qdbus6 >/dev/null 2>&1; then
    qdbus_bin="qdbus6"
  fi

  if [[ -n "$qdbus_bin" ]]; then
    target_uri="file://$target"
    script=$(cat <<EOF
var desktopsArray = desktops();
for (var i = 0; i < desktopsArray.length; i++) {
    var desktop = desktopsArray[i];
    desktop.wallpaperPlugin = "org.kde.image";
    desktop.currentConfigGroup = ["Wallpaper", "org.kde.image", "General"];
    desktop.writeConfig("Image", "$target_uri");
    desktop.writeConfig("PreviewImage", "null");
    desktop.writeConfig("FillMode", 2);
}
EOF
)
    "$qdbus_bin" org.kde.plasmashell /PlasmaShell org.kde.PlasmaShell.evaluateScript "$script" >/dev/null 2>&1 || \
      "$qdbus_bin" org.kde.plasmashell /PlasmaShell evaluateScript "$script" >/dev/null 2>&1 || true
  elif [[ -n "${DISPLAY:-}" ]] && command -v feh >/dev/null 2>&1; then
    feh --no-fehbg --bg-fill "$target" >/dev/null 2>&1 || true
  fi
  printf '%s\n' "$target"
}

pick_next() {
  local current="$1"
  local count="${#WALLPAPERS[@]}"
  local idx=0
  local i
  for i in "${!WALLPAPERS[@]}"; do
    if [[ "${WALLPAPERS[$i]}" == "$current" ]]; then
      idx="$i"
      break
    fi
  done
  printf '%s\n' "${WALLPAPERS[$(((idx + 1) % count))]}"
}

pick_prev() {
  local current="$1"
  local count="${#WALLPAPERS[@]}"
  local idx=0
  local i
  for i in "${!WALLPAPERS[@]}"; do
    if [[ "${WALLPAPERS[$i]}" == "$current" ]]; then
      idx="$i"
      break
    fi
  done
  printf '%s\n' "${WALLPAPERS[$(((idx - 1 + count) % count))]}"
}

main() {
  local cmd="${1:-apply-current}"
  local current target

  load_wallpapers

  case "$cmd" in
    apply-current)
      current="$(current_wallpaper)" || exit 1
      apply_wallpaper "$current"
      ;;
    set)
      target="${2:-}"
      if [[ -z "$target" || ! -f "$target" ]]; then
        echo "Wallpaper not found: $target" >&2
        exit 1
      fi
      apply_wallpaper "$target"
      ;;
    next)
      [[ "${#WALLPAPERS[@]}" -gt 0 ]] || { echo "No wallpapers available in $WALL_DIR" >&2; exit 1; }
      current="$(current_wallpaper || true)"
      if [[ -z "$current" || ! -f "$current" ]]; then
        current="${WALLPAPERS[0]}"
      fi
      target="$(pick_next "$current")"
      apply_wallpaper "$target"
      ;;
    prev)
      [[ "${#WALLPAPERS[@]}" -gt 0 ]] || { echo "No wallpapers available in $WALL_DIR" >&2; exit 1; }
      current="$(current_wallpaper || true)"
      if [[ -z "$current" || ! -f "$current" ]]; then
        current="${WALLPAPERS[0]}"
      fi
      target="$(pick_prev "$current")"
      apply_wallpaper "$target"
      ;;
    random)
      [[ "${#WALLPAPERS[@]}" -gt 0 ]] || { echo "No wallpapers available in $WALL_DIR" >&2; exit 1; }
      target="${WALLPAPERS[$((RANDOM % ${#WALLPAPERS[@]}))]}"
      apply_wallpaper "$target"
      ;;
    list)
      printf '%s\n' "${WALLPAPERS[@]}"
      ;;
    status)
      current_wallpaper || true
      ;;
    *)
      usage
      exit 1
      ;;
  esac
}

main "$@"
