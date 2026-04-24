#!/usr/bin/env bash
set -Eeuo pipefail

SDDM_AUTOLOGIN_FILE="/etc/sddm.conf.d/20-crixa-autologin.conf"
WAYLAND_SESSION="plasmawayland.desktop"
X11_SESSION="plasma.desktop"

usage() {
  cat <<'EOF'
Usage:
  crixa-session-mode status
  crixa-session-mode set x11|wayland
  crixa-session-mode toggle
EOF
}

ensure_root() {
  if [[ "$EUID" -ne 0 ]]; then
    exec sudo -n /usr/local/bin/crixa-session-mode "$@"
  fi
}

current_session() {
  if [[ -f "$SDDM_AUTOLOGIN_FILE" ]]; then
    awk -F= '/^\s*Session=/{print $2; exit}' "$SDDM_AUTOLOGIN_FILE"
    return
  fi
  printf '%s\n' "$X11_SESSION"
}

current_user() {
  if [[ -f "$SDDM_AUTOLOGIN_FILE" ]]; then
    awk -F= '/^\s*User=/{print $2; exit}' "$SDDM_AUTOLOGIN_FILE"
    return
  fi
  printf '%s\n' "${SUDO_USER:-$(id -un)}"
}

current_mode() {
  local session
  session="$(current_session)"
  if [[ "$session" == "$WAYLAND_SESSION" ]]; then
    printf 'wayland\n'
  else
    printf 'x11\n'
  fi
}

write_mode() {
  local mode="$1"
  local user
  local session="$X11_SESSION"
  user="$(current_user)"
  if [[ "$mode" == "wayland" ]]; then
    session="$WAYLAND_SESSION"
  fi

  mkdir -p "$(dirname "$SDDM_AUTOLOGIN_FILE")"
  cat > "$SDDM_AUTOLOGIN_FILE" <<EOF
[Autologin]
User=$user
Session=$session
Relogin=false
EOF
}

main() {
  local cmd="${1:-status}"
  case "$cmd" in
    status)
      printf 'mode=%s\n' "$(current_mode)"
      printf 'session=%s\n' "$(current_session)"
      ;;
    set)
      local mode="${2:-}"
      [[ "$mode" == "x11" || "$mode" == "wayland" ]] || {
        echo "Invalid mode: $mode" >&2
        exit 1
      }
      ensure_root "$@"
      write_mode "$mode"
      printf 'mode=%s\n' "$mode"
      ;;
    toggle)
      local next="wayland"
      [[ "$(current_mode)" == "wayland" ]] && next="x11"
      ensure_root "$@"
      write_mode "$next"
      printf 'mode=%s\n' "$next"
      ;;
    -h|--help)
      usage
      ;;
    *)
      usage
      exit 1
      ;;
  esac
}

main "$@"
