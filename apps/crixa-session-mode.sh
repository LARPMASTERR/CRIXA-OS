#!/usr/bin/env bash
set -Eeuo pipefail

LIGHTDM_FILE="/etc/lightdm/lightdm.conf.d/50-crixa-autologin.conf"
WAYLAND_SESSION="crixa-wayland"
X11_SESSION="openbox"

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
  if [[ -f "$LIGHTDM_FILE" ]]; then
    awk -F= '/^\s*user-session=/{print $2; exit}' "$LIGHTDM_FILE"
    return
  fi
  printf '%s\n' "$X11_SESSION"
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
  local session="$X11_SESSION"
  if [[ "$mode" == "wayland" ]]; then
    session="$WAYLAND_SESSION"
  fi

  mkdir -p "$(dirname "$LIGHTDM_FILE")"
  if [[ ! -f "$LIGHTDM_FILE" ]]; then
    cat > "$LIGHTDM_FILE" <<EOF
[Seat:*]
autologin-user=crixa
autologin-user-timeout=0
user-session=$session
greeter-hide-users=true
allow-guest=false
EOF
    return
  fi

  if grep -q '^\s*user-session=' "$LIGHTDM_FILE"; then
    sed -i "s/^\s*user-session=.*/user-session=$session/" "$LIGHTDM_FILE"
  else
    printf 'user-session=%s\n' "$session" >> "$LIGHTDM_FILE"
  fi
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
