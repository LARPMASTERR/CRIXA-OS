#!/usr/bin/env bash
set -Eeuo pipefail

show_help() {
  cat <<'EOF'
crixa-fetch: CRIXA OS system info card

Usage:
  crixa-fetch [--no-color]
  fastfetch
  neofetch
EOF
}

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
  show_help
  exit 0
fi

NO_COLOR_MODE=0
if [[ "${1:-}" == "--no-color" ]]; then
  NO_COLOR_MODE=1
  shift
fi

if [[ "$NO_COLOR_MODE" -eq 0 && -n "${NO_COLOR:-}" ]]; then
  NO_COLOR_MODE=1
fi

if [[ "$NO_COLOR_MODE" -eq 0 ]]; then
  C0=$'\033[0m'
  C1=$'\033[38;5;39m'
  C2=$'\033[38;5;45m'
  C3=$'\033[38;5;75m'
  C4=$'\033[38;5;117m'
else
  C0=""
  C1=""
  C2=""
  C3=""
  C4=""
fi

format_memory() {
  awk '
    /MemTotal/ { total = $2 }
    /MemAvailable/ { avail = $2 }
    END {
      used = total - avail
      if (total <= 0) {
        print "n/a"
        exit
      }
      printf "%.1fGiB / %.1fGiB", used / 1048576, total / 1048576
    }
  ' /proc/meminfo 2>/dev/null || echo "n/a"
}

get_packages() {
  if command -v dpkg-query >/dev/null 2>&1; then
    dpkg-query -W -f='${binary:Package}\n' 2>/dev/null | wc -l | tr -d ' '
  else
    echo "n/a"
  fi
}

get_cpu() {
  awk -F: '/model name/{gsub(/^[ \t]+/, "", $2); print $2; exit}' /proc/cpuinfo 2>/dev/null || echo "n/a"
}

get_gpu() {
  if command -v lspci >/dev/null 2>&1; then
    lspci 2>/dev/null | awk -F': ' '/VGA compatible controller|3D controller|Display controller/{print $2; exit}' || true
  fi
  return 0
}

get_resolution() {
  if [[ -n "${DISPLAY:-}" ]] && command -v xrandr >/dev/null 2>&1; then
    xrandr --current 2>/dev/null | awk '/\*/{print $1; exit}' || true
    return 0
  fi
  if command -v kscreen-doctor >/dev/null 2>&1; then
    kscreen-doctor -o 2>/dev/null | grep -oE '[0-9]+x[0-9]+@[0-9.]+\*[!]?' | head -n 1 | cut -d@ -f1 || true
  fi
  return 0
}

normalize_desktop_name() {
  local raw="$1"
  case "$raw" in
    KDE|KDE\ Plasma|plasma|Plasma|plasmawayland|plasma.desktop|plasmawayland.desktop)
      echo "Plasma"
      ;;
    "")
      echo "n/a"
      ;;
    *)
      echo "$raw"
      ;;
  esac
}

normalize_wm_name() {
  local raw="$1"
  case "$raw" in
    KWin|KWin\ X11|KWin\ Wayland|kwin_x11|kwin_wayland)
      echo "KWin"
      ;;
    "")
      echo "n/a"
      ;;
    *)
      echo "$raw"
      ;;
  esac
}

get_de() {
  if [[ -n "${XDG_CURRENT_DESKTOP:-}" ]]; then
    normalize_desktop_name "${XDG_CURRENT_DESKTOP%%:*}"
    return
  fi
  if [[ -n "${XDG_SESSION_DESKTOP:-}" ]]; then
    normalize_desktop_name "$XDG_SESSION_DESKTOP"
    return
  fi
  echo "n/a"
}

get_wm() {
  if command -v xprop >/dev/null 2>&1 && [[ -n "${DISPLAY:-}" ]]; then
    local wm_id
    wm_id="$(xprop -root _NET_SUPPORTING_WM_CHECK 2>/dev/null | awk -F' #' '/_NET_SUPPORTING_WM_CHECK/{print $2}' | tr -d ' ' || true)"
    if [[ -n "$wm_id" ]]; then
      local wm_name
      wm_name="$(xprop -id "$wm_id" _NET_WM_NAME 2>/dev/null | sed -n 's/.*= "\(.*\)"/\1/p' || true)"
      if [[ -n "$wm_name" ]]; then
        normalize_wm_name "$wm_name"
        return
      fi
    fi
  fi
  if pgrep -x kwin_x11 >/dev/null 2>&1 || pgrep -x kwin_wayland >/dev/null 2>&1; then
    normalize_wm_name "kwin_x11"
    return
  fi
  echo "n/a"
}

get_session_type() {
  case "${XDG_SESSION_TYPE:-}" in
    x11)
      echo "X11"
      ;;
    wayland)
      echo "Wayland"
      ;;
    "")
      if [[ -n "${WAYLAND_DISPLAY:-}" ]]; then
        echo "Wayland"
      elif [[ -n "${DISPLAY:-}" ]]; then
        echo "X11"
      else
        echo "n/a"
      fi
      ;;
    *)
      echo "${XDG_SESSION_TYPE}"
      ;;
  esac
}

get_theme() {
  local theme=""
  local config_cmd
  for config_cmd in kreadconfig6 kreadconfig5 kreadconfig; do
    if command -v "$config_cmd" >/dev/null 2>&1; then
      theme="$("$config_cmd" --file kdeglobals --group General --key ColorScheme 2>/dev/null || true)"
      [[ -n "$theme" ]] && break
    fi
  done
  if [[ -z "$theme" && -f "$HOME/.config/gtk-3.0/settings.ini" ]]; then
    theme="$(awk -F= '/^gtk-theme-name=/{print $2; exit}' "$HOME/.config/gtk-3.0/settings.ini" 2>/dev/null || true)"
  fi
  if [[ -z "$theme" && -f "/etc/skel/.config/gtk-3.0/settings.ini" ]]; then
    theme="$(awk -F= '/^gtk-theme-name=/{print $2; exit}' "/etc/skel/.config/gtk-3.0/settings.ini" 2>/dev/null || true)"
  fi
  if [[ -z "$theme" ]]; then
    theme="CRIXA"
  fi
  echo "$theme"
}

get_uptime() {
  uptime -p 2>/dev/null | sed 's/^up //' || echo "n/a"
}

kv() {
  local key="$1"
  local value="$2"
  printf "%b%-11s%b %s" "$C2" "$key" "$C0" "$value"
}

HOSTNAME_VALUE="$(hostname 2>/dev/null || echo "crixa-os")"
KERNEL_VALUE="$(uname -r 2>/dev/null || echo "n/a")"
UPTIME_VALUE="$(get_uptime)"
PACKAGES_VALUE="$(get_packages)"
SHELL_VALUE="$(basename "${SHELL:-bash}")"
RESOLUTION_VALUE="$(get_resolution)"
DE_VALUE="$(get_de)"
WM_VALUE="$(get_wm)"
SESSION_VALUE="$(get_session_type)"
THEME_VALUE="$(get_theme)"
CPU_VALUE="$(get_cpu || true)"
GPU_VALUE="$(get_gpu || true)"
MEMORY_VALUE="$(format_memory)"

if [[ -z "$RESOLUTION_VALUE" ]]; then
  RESOLUTION_VALUE="n/a"
fi
if [[ -z "$GPU_VALUE" ]]; then
  GPU_VALUE="n/a"
fi

ASCII_LINES=(
  "${C1}        .-===========-.${C0}"
  "${C1}      .:++***###***++:.${C0}"
  "${C1}     :+**${C3}CRIXA OS${C1}**+:${C0}"
  "${C1}    :+**${C4}########${C1}**+:${C0}"
  "${C1}   .+**${C4}##########${C1}**+.${C0}"
  "${C1}   :+**${C4}####${C3}..${C4}####${C1}**+:${C0}"
  "${C1}   :+**${C4}####${C3}..${C4}####${C1}**+:${C0}"
  "${C1}   .+**${C4}##########${C1}**+.${C0}"
  "${C1}    :+**${C4}########${C1}**+:${C0}"
  "${C1}     :+**${C3}CRIXA${C1}**+:${C0}"
  "${C1}      .:++***###***++:.${C0}"
  "${C1}        '-==========-'${C0}"
)

INFO_LINES=(
  "$(kv "OS" "CRIXA OS v0 (Debian)")"
  "$(kv "Host" "$HOSTNAME_VALUE")"
  "$(kv "Kernel" "$KERNEL_VALUE")"
  "$(kv "Uptime" "$UPTIME_VALUE")"
  "$(kv "Packages" "$PACKAGES_VALUE")"
  "$(kv "Shell" "$SHELL_VALUE")"
  "$(kv "Resolution" "$RESOLUTION_VALUE")"
  "$(kv "DE" "$DE_VALUE")"
  "$(kv "WM" "$WM_VALUE")"
  "$(kv "Session" "$SESSION_VALUE")"
  "$(kv "Theme" "$THEME_VALUE")"
  "$(kv "CPU" "$CPU_VALUE")"
  "$(kv "GPU" "$GPU_VALUE")"
  "$(kv "Memory" "$MEMORY_VALUE")"
)

MAX_LINES="${#ASCII_LINES[@]}"
if (( ${#INFO_LINES[@]} > MAX_LINES )); then
  MAX_LINES="${#INFO_LINES[@]}"
fi

for ((i = 0; i < MAX_LINES; i++)); do
  printf "%-34b  %b\n" "${ASCII_LINES[i]:-}" "${INFO_LINES[i]:-}"
done

if [[ "$NO_COLOR_MODE" -eq 0 ]]; then
  printf "\n  "
  for block in 27 33 39 45 51 69 75 117; do
    printf "\033[48;5;%sm  \033[0m" "$block"
  done
  printf "\n"
fi
