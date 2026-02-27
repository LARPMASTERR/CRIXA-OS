#!/usr/bin/env bash
set -Eeuo pipefail

CONFIG_HOME="${XDG_CONFIG_HOME:-$HOME/.config}"
PROFILE_DIR="$CONFIG_HOME/crixa/firefox-profile"
USER_JS="$PROFILE_DIR/user.js"

ensure_profile() {
  mkdir -p "$PROFILE_DIR"
  if [[ ! -f "$USER_JS" ]]; then
    : > "$USER_JS"
  fi

  set_pref "browser.shell.checkDefaultBrowser" "false"
  set_pref "browser.startup.homepage_override.mstone" "\"ignore\""
  set_pref "browser.aboutwelcome.enabled" "false"
  set_pref "toolkit.telemetry.reportingpolicy.firstRun" "false"
  set_pref "datareporting.policy.dataSubmissionEnabled" "false"
  set_pref "toolkit.cosmeticAnimations.enabled" "false"
  set_pref "ui.prefersReducedMotion" "1"
  set_pref "browser.tabs.animate" "false"
  set_pref "browser.tabs.unloadOnLowMemory" "true"
  set_pref "browser.sessionstore.interval" "120000"
  set_pref "dom.ipc.processCount" "2"
  set_pref "dom.ipc.processCount.webIsolated" "1"
  set_pref "browser.cache.disk.enable" "false"
  set_pref "browser.cache.memory.enable" "true"
  set_pref "general.smoothScroll" "false"
  set_pref "gfx.webrender.software" "true"
  set_pref "media.autoplay.default" "0"
  set_pref "media.autoplay.blocking_policy" "0"
  set_pref "media.av1.enabled" "false"
  set_pref "media.hardware-video-decoding.force-enabled" "false"
  set_pref "layers.acceleration.disabled" "false"
  set_pref "gfx.webrender.force-disabled" "false"
  set_pref "media.ffmpeg.vaapi.enabled" "false"
  set_pref "widget.gtk.non-native-titlebar.enabled" "false"
}

set_pref() {
  local key="$1"
  local value="$2"
  local tmp
  tmp="$(mktemp)"
  awk -v key="$key" -v value="$value" '
    BEGIN { found = 0; prefix = "user_pref(\"" key "\"," }
    index($0, prefix) == 1 {
      print "user_pref(\"" key "\", " value ");"
      found = 1
      next
    }
    { print }
    END {
      if (!found) {
        print "user_pref(\"" key "\", " value ");"
      }
    }
  ' "$USER_JS" > "$tmp"
  mv "$tmp" "$USER_JS"
}

set_render_mode() {
  local has_dri=0
  if [[ -e /dev/dri/renderD128 || -e /dev/dri/card0 ]]; then
    has_dri=1
  fi

  export MOZ_ENABLE_WAYLAND=0
  export MOZ_X11_EGL=0
  export MOZ_GTK_TITLEBAR_DECORATION=system

  # If no DRI device exists, prefer deterministic software mode.
  if [[ "$has_dri" -eq 0 ]]; then
    export MOZ_WEBRENDER=1
    return
  fi

  unset MOZ_WEBRENDER 2>/dev/null || true
  unset LIBGL_ALWAYS_SOFTWARE 2>/dev/null || true
}

if command -v firefox-esr >/dev/null 2>&1; then
  ensure_profile
  set_render_mode

  if [[ "$#" -gt 0 ]]; then
    exec firefox-esr --profile "$PROFILE_DIR" --no-remote "$@"
  fi
  exec firefox-esr --profile "$PROFILE_DIR" --no-remote
fi

if command -v firefox >/dev/null 2>&1; then
  if [[ "$#" -gt 0 ]]; then
    exec firefox "$@"
  fi
  exec firefox
fi

if command -v flatpak >/dev/null 2>&1 && flatpak info org.mozilla.firefox >/dev/null 2>&1; then
  if [[ "$#" -gt 0 ]]; then
    exec flatpak run org.mozilla.firefox "$@"
  fi
  exec flatpak run org.mozilla.firefox
fi

if command -v xdg-open >/dev/null 2>&1; then
  if [[ "$#" -gt 0 ]]; then
    exec xdg-open "$1"
  fi
fi

exit 1
