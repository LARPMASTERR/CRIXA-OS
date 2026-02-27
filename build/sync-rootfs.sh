#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
ROOTFS_DIR="${ROOTFS_DIR:-$PROJECT_ROOT/rootfs}"
LIVE_USER="${LIVE_USER:-crixa}"
DIST="${DIST:-bookworm}"
MIRROR="${MIRROR:-https://deb.debian.org/debian}"
SYNC_ENABLE_APT="${SYNC_ENABLE_APT:-0}"
CRIXA_VERSION="${CRIXA_VERSION:-0.0.0}"
CRIXA_TRACK="${CRIXA_TRACK:-stable}"
CRIXA_BUILD_ID="${CRIXA_BUILD_ID:-manual-sync}"
CHROOT_MOUNTS_ACTIVE=0

cleanup_chroot_mounts() {
  if [[ "$CHROOT_MOUNTS_ACTIVE" != "1" ]]; then
    return
  fi
  local mount_path
  for mount_path in "$ROOTFS_DIR/dev/pts" "$ROOTFS_DIR/dev" "$ROOTFS_DIR/proc" "$ROOTFS_DIR/sys"; do
    if mountpoint -q "$mount_path"; then
      umount -lf "$mount_path" || true
    fi
  done
  CHROOT_MOUNTS_ACTIVE=0
}

mount_chroot_filesystems() {
  mkdir -p "$ROOTFS_DIR/dev/pts" "$ROOTFS_DIR/proc" "$ROOTFS_DIR/sys"
  if ! mountpoint -q "$ROOTFS_DIR/dev"; then
    mount --bind /dev "$ROOTFS_DIR/dev"
  fi
  if ! mountpoint -q "$ROOTFS_DIR/dev/pts"; then
    mount --bind /dev/pts "$ROOTFS_DIR/dev/pts"
  fi
  if ! mountpoint -q "$ROOTFS_DIR/proc"; then
    mount -t proc proc "$ROOTFS_DIR/proc"
  fi
  if ! mountpoint -q "$ROOTFS_DIR/sys"; then
    mount -t sysfs sys "$ROOTFS_DIR/sys"
  fi
  if [[ -e /etc/resolv.conf ]]; then
    cp -L /etc/resolv.conf "$ROOTFS_DIR/etc/resolv.conf" || true
  fi
  CHROOT_MOUNTS_ACTIVE=1
}

trap cleanup_chroot_mounts EXIT

require_file() {
  local file_path="$1"
  [[ -f "$file_path" ]] || {
    echo "Missing required file: $file_path"
    exit 1
  }
}

ensure_bashrc_snippet() {
  local target="$1"
  local marker="# --- CRIXA FETCH ---"
  if [[ ! -f "$target" ]]; then
    return
  fi
  if ! grep -qF "$marker" "$target"; then
    printf '\n' >> "$target"
    cat "$PROJECT_ROOT/ui-shell/bashrc-crixa-snippet" >> "$target"
    printf '\n' >> "$target"
  fi
}

if [[ ! -d "$ROOTFS_DIR/etc" ]]; then
  echo "Project rootfs not found at: $ROOTFS_DIR"
  echo "Run a full build once before using sync-rootfs.sh."
  exit 1
fi

require_file "$PROJECT_ROOT/ui-shell/rc.xml"
require_file "$PROJECT_ROOT/ui-shell/menu.xml"
require_file "$PROJECT_ROOT/ui-shell/autostart"
require_file "$PROJECT_ROOT/ui-shell/tint2rc"
require_file "$PROJECT_ROOT/ui-shell/rofi.rasi"
require_file "$PROJECT_ROOT/ui-shell/gtk-settings.ini"
require_file "$PROJECT_ROOT/ui-shell/thunar-uca.xml"
require_file "$PROJECT_ROOT/ui-shell/thunarrc"
require_file "$PROJECT_ROOT/ui-shell/xorg-input.conf"
require_file "$PROJECT_ROOT/ui-shell/picom.conf"
require_file "$PROJECT_ROOT/themes/CRIXA/gtk.css"
require_file "$PROJECT_ROOT/themes/CRIXA/index.theme"
require_file "$PROJECT_ROOT/themes/CRIXA/openbox-themerc"
require_file "$PROJECT_ROOT/ui-shell/bashrc-crixa-snippet"
require_file "$PROJECT_ROOT/apps/crixa-fetch.sh"
require_file "$PROJECT_ROOT/apps/crixa-screenshot.sh"
require_file "$PROJECT_ROOT/apps/neofetch.sh"
require_file "$PROJECT_ROOT/apps/crixapkg.sh"
require_file "$PROJECT_ROOT/apps/crixapkg.py"
require_file "$PROJECT_ROOT/apps/crixa-settings.py"
require_file "$PROJECT_ROOT/apps/crixa-store.py"
require_file "$PROJECT_ROOT/apps/crixa-store.sh"
require_file "$PROJECT_ROOT/apps/crixa-store.desktop"
require_file "$PROJECT_ROOT/apps/crixa-installer.sh"
require_file "$PROJECT_ROOT/apps/crixa-installer.py"
require_file "$PROJECT_ROOT/apps/crixa-install.sh"
require_file "$PROJECT_ROOT/apps/crixa-installer.desktop"
require_file "$PROJECT_ROOT/apps/crixa-updater.sh"
require_file "$PROJECT_ROOT/apps/crixa-updater.py"
require_file "$PROJECT_ROOT/apps/crixa-updater.desktop"
require_file "$PROJECT_ROOT/apps/crixa-session-mode.sh"
require_file "$PROJECT_ROOT/apps/crixa-wayland-session.sh"
require_file "$PROJECT_ROOT/apps/crixa-wayland-session.desktop"
require_file "$PROJECT_ROOT/apps/crixa-wayland-control.sh"
require_file "$PROJECT_ROOT/apps/crixa-wayland-control.py"
require_file "$PROJECT_ROOT/apps/crixa-wayland-control.desktop"
require_file "$PROJECT_ROOT/apps/crixa-releasectl.sh"
require_file "$PROJECT_ROOT/apps/crixa-releasectl.py"
require_file "$PROJECT_ROOT/ui-shell-wayland/labwc/autostart"
require_file "$PROJECT_ROOT/ui-shell-wayland/labwc/environment"
require_file "$PROJECT_ROOT/ui-shell-wayland/waybar/config"
require_file "$PROJECT_ROOT/ui-shell-wayland/waybar/style.css"
require_file "$PROJECT_ROOT/ui-shell-wayland/wofi/config"
require_file "$PROJECT_ROOT/ui-shell-wayland/wofi/style.css"
require_file "$PROJECT_ROOT/store-backends/backend-crixa-repo.py"
require_file "$PROJECT_ROOT/store-backends/backend-flatpak.py"
require_file "$PROJECT_ROOT/store-backends/manifests/crixa-repo.json"
require_file "$PROJECT_ROOT/store-backends/manifests/flathub.json"
require_file "$PROJECT_ROOT/store-backends/extensions/README.md"
require_file "$PROJECT_ROOT/store-backends/extensions/example-template.py"
require_file "$PROJECT_ROOT/build/build-crixa-repo.sh"
require_file "$PROJECT_ROOT/store-packages/catalog.json"
require_file "$PROJECT_ROOT/store-packages/system-rollouts.json"
require_file "$PROJECT_ROOT/store-packages/packages/lumen-notes/payload/bin/lumen-notes"
require_file "$PROJECT_ROOT/store-packages/packages/lumen-notes/payload/applications/lumen-notes.desktop"
require_file "$PROJECT_ROOT/store-packages/packages/lumen-notes/payload/icons/hicolor/scalable/apps/lumen-notes.svg"
require_file "$PROJECT_ROOT/store-packages/packages/orbit-tasks/payload/bin/orbit-tasks"
require_file "$PROJECT_ROOT/store-packages/packages/orbit-tasks/payload/applications/orbit-tasks.desktop"
require_file "$PROJECT_ROOT/store-packages/packages/orbit-tasks/payload/icons/hicolor/scalable/apps/orbit-tasks.svg"
require_file "$PROJECT_ROOT/store-packages/packages/media-lab/payload/bin/media-lab"
require_file "$PROJECT_ROOT/store-packages/packages/media-lab/payload/applications/media-lab.desktop"
require_file "$PROJECT_ROOT/store-packages/packages/media-lab/payload/icons/hicolor/scalable/apps/media-lab.svg"
require_file "$PROJECT_ROOT/assets/icons/crixa-launcher.svg"
require_file "$PROJECT_ROOT/assets/icons/crixa-settings.svg"
require_file "$PROJECT_ROOT/assets/icons/crixa-store.svg"
require_file "$PROJECT_ROOT/assets/icons/crixa-browser.svg"
require_file "$PROJECT_ROOT/assets/icons/crixa-files.svg"
require_file "$PROJECT_ROOT/assets/icons/crixa-terminal.svg"
require_file "$PROJECT_ROOT/assets/icons/crixa-task-manager.svg"
require_file "$PROJECT_ROOT/assets/icons/crixa-wallpapers.svg"
require_file "$PROJECT_ROOT/assets/icons/crixa-installer.svg"
require_file "$PROJECT_ROOT/assets/icons/crixa-updater.svg"
require_file "$PROJECT_ROOT/assets/icons/crixa-wayland-control.svg"
require_file "$PROJECT_ROOT/assets/icons/crixa-youtube.svg"
require_file "$PROJECT_ROOT/assets/icons/LICENSE.txt"

chmod +x "$PROJECT_ROOT/build/build-crixa-repo.sh"
"$PROJECT_ROOT/build/build-crixa-repo.sh"
require_file "$PROJECT_ROOT/crixa-repo/metadata/repo.json"
require_file "$PROJECT_ROOT/crixa-repo/metadata/repo.sig"
require_file "$PROJECT_ROOT/crixa-repo/metadata/system-updates.json"
require_file "$PROJECT_ROOT/crixa-repo/metadata/system-updates.sig"
require_file "$PROJECT_ROOT/crixa-repo/keys/repo-public.pem"

install -d "$ROOTFS_DIR/usr/share/themes/CRIXA/gtk-3.0"
install -d "$ROOTFS_DIR/usr/share/themes/CRIXA/openbox-3"
install -m 0644 "$PROJECT_ROOT/themes/CRIXA/gtk.css" "$ROOTFS_DIR/usr/share/themes/CRIXA/gtk-3.0/gtk.css"
install -m 0644 "$PROJECT_ROOT/themes/CRIXA/index.theme" "$ROOTFS_DIR/usr/share/themes/CRIXA/index.theme"
install -m 0644 "$PROJECT_ROOT/themes/CRIXA/openbox-themerc" "$ROOTFS_DIR/usr/share/themes/CRIXA/openbox-3/themerc"

install -d "$ROOTFS_DIR/usr/share/backgrounds"
install -d "$ROOTFS_DIR/usr/share/backgrounds/crixa"
install -m 0644 "$PROJECT_ROOT/assets/wallpapers/crixa-wallpaper.jpg" "$ROOTFS_DIR/usr/share/backgrounds/crixa-wallpaper.jpg"
install -m 0644 "$PROJECT_ROOT/assets/wallpapers/crixa-wallpaper.svg" "$ROOTFS_DIR/usr/share/backgrounds/crixa-wallpaper.svg"
install -m 0644 "$PROJECT_ROOT/assets/wallpapers/crixa-wallpaper.jpg" "$ROOTFS_DIR/usr/share/backgrounds/crixa/00-crixa-default.jpg"
install -m 0644 "$PROJECT_ROOT/assets/wallpapers/crixa-wallpaper-orbit.jpg" "$ROOTFS_DIR/usr/share/backgrounds/crixa/10-crixa-orbit.jpg"
install -m 0644 "$PROJECT_ROOT/assets/wallpapers/crixa-wallpaper-nebula.jpg" "$ROOTFS_DIR/usr/share/backgrounds/crixa/20-crixa-nebula.jpg"
install -m 0644 "$PROJECT_ROOT/assets/wallpapers/crixa-wallpaper-planet.jpg" "$ROOTFS_DIR/usr/share/backgrounds/crixa/30-crixa-planet.jpg"
install -m 0644 "$PROJECT_ROOT/assets/wallpapers/crixa-wallpaper-saturn.jpg" "$ROOTFS_DIR/usr/share/backgrounds/crixa/40-crixa-saturn.jpg"
install -m 0644 "$PROJECT_ROOT/assets/wallpapers/crixa-wallpaper-jupiter.jpg" "$ROOTFS_DIR/usr/share/backgrounds/crixa/50-crixa-jupiter.jpg"
install -m 0644 "$PROJECT_ROOT/assets/wallpapers/crixa-wallpaper-aurora.jpg" "$ROOTFS_DIR/usr/share/backgrounds/crixa/60-crixa-aurora.jpg"
install -m 0644 "$PROJECT_ROOT/assets/wallpapers/crixa-wallpaper-rings.jpg" "$ROOTFS_DIR/usr/share/backgrounds/crixa/70-crixa-rings.jpg"
install -m 0644 "$PROJECT_ROOT/assets/wallpapers/crixa-wallpaper-uranus.jpg" "$ROOTFS_DIR/usr/share/backgrounds/crixa/80-crixa-uranus.jpg"

install -d "$ROOTFS_DIR/usr/share/icons/hicolor/scalable/apps"
install -m 0644 "$PROJECT_ROOT/assets/icons/crixa-launcher.svg" "$ROOTFS_DIR/usr/share/icons/hicolor/scalable/apps/crixa-launcher.svg"
install -m 0644 "$PROJECT_ROOT/assets/icons/crixa-settings.svg" "$ROOTFS_DIR/usr/share/icons/hicolor/scalable/apps/crixa-settings.svg"
install -m 0644 "$PROJECT_ROOT/assets/icons/crixa-store.svg" "$ROOTFS_DIR/usr/share/icons/hicolor/scalable/apps/crixa-store.svg"
install -m 0644 "$PROJECT_ROOT/assets/icons/crixa-browser.svg" "$ROOTFS_DIR/usr/share/icons/hicolor/scalable/apps/crixa-browser.svg"
install -m 0644 "$PROJECT_ROOT/assets/icons/crixa-files.svg" "$ROOTFS_DIR/usr/share/icons/hicolor/scalable/apps/crixa-files.svg"
install -m 0644 "$PROJECT_ROOT/assets/icons/crixa-terminal.svg" "$ROOTFS_DIR/usr/share/icons/hicolor/scalable/apps/crixa-terminal.svg"
install -m 0644 "$PROJECT_ROOT/assets/icons/crixa-task-manager.svg" "$ROOTFS_DIR/usr/share/icons/hicolor/scalable/apps/crixa-task-manager.svg"
install -m 0644 "$PROJECT_ROOT/assets/icons/crixa-wallpapers.svg" "$ROOTFS_DIR/usr/share/icons/hicolor/scalable/apps/crixa-wallpapers.svg"
install -m 0644 "$PROJECT_ROOT/assets/icons/crixa-installer.svg" "$ROOTFS_DIR/usr/share/icons/hicolor/scalable/apps/crixa-installer.svg"
install -m 0644 "$PROJECT_ROOT/assets/icons/crixa-updater.svg" "$ROOTFS_DIR/usr/share/icons/hicolor/scalable/apps/crixa-updater.svg"
install -m 0644 "$PROJECT_ROOT/assets/icons/crixa-wayland-control.svg" "$ROOTFS_DIR/usr/share/icons/hicolor/scalable/apps/crixa-wayland-control.svg"
install -m 0644 "$PROJECT_ROOT/assets/icons/crixa-youtube.svg" "$ROOTFS_DIR/usr/share/icons/hicolor/scalable/apps/crixa-youtube.svg"

install -d "$ROOTFS_DIR/usr/local/bin"
install -m 0755 "$PROJECT_ROOT/apps/crixa-settings.sh" "$ROOTFS_DIR/usr/local/bin/crixa-settings"
install -m 0755 "$PROJECT_ROOT/apps/crixa-settings.py" "$ROOTFS_DIR/usr/local/bin/crixa-settings.py"
install -m 0755 "$PROJECT_ROOT/apps/crixa-store.sh" "$ROOTFS_DIR/usr/local/bin/crixa-store"
install -m 0755 "$PROJECT_ROOT/apps/crixa-store.py" "$ROOTFS_DIR/usr/local/bin/crixa-store.py"
install -m 0755 "$PROJECT_ROOT/apps/crixa-installer.sh" "$ROOTFS_DIR/usr/local/bin/crixa-installer"
install -m 0755 "$PROJECT_ROOT/apps/crixa-installer.py" "$ROOTFS_DIR/usr/local/bin/crixa-installer.py"
install -m 0755 "$PROJECT_ROOT/apps/crixa-updater.sh" "$ROOTFS_DIR/usr/local/bin/crixa-updater"
install -m 0755 "$PROJECT_ROOT/apps/crixa-updater.py" "$ROOTFS_DIR/usr/local/bin/crixa-updater.py"
install -m 0755 "$PROJECT_ROOT/apps/crixa-session-mode.sh" "$ROOTFS_DIR/usr/local/bin/crixa-session-mode"
install -m 0755 "$PROJECT_ROOT/apps/crixa-wayland-session.sh" "$ROOTFS_DIR/usr/local/bin/crixa-wayland-session"
install -m 0755 "$PROJECT_ROOT/apps/crixa-wayland-control.sh" "$ROOTFS_DIR/usr/local/bin/crixa-wayland-control"
install -m 0755 "$PROJECT_ROOT/apps/crixa-wayland-control.py" "$ROOTFS_DIR/usr/local/bin/crixa-wayland-control.py"
install -m 0755 "$PROJECT_ROOT/apps/crixa-releasectl.sh" "$ROOTFS_DIR/usr/local/bin/crixa-releasectl"
install -m 0755 "$PROJECT_ROOT/apps/crixa-releasectl.py" "$ROOTFS_DIR/usr/local/bin/crixa-releasectl.py"
install -m 0755 "$PROJECT_ROOT/apps/crixapkg.sh" "$ROOTFS_DIR/usr/local/bin/crixapkg"
install -m 0755 "$PROJECT_ROOT/apps/crixapkg.py" "$ROOTFS_DIR/usr/local/bin/crixapkg.py"
install -m 0755 "$PROJECT_ROOT/apps/crixa-browser.sh" "$ROOTFS_DIR/usr/local/bin/crixa-browser"
install -m 0755 "$PROJECT_ROOT/apps/crixa-terminal.sh" "$ROOTFS_DIR/usr/local/bin/crixa-terminal"
install -m 0755 "$PROJECT_ROOT/apps/crixa-files.sh" "$ROOTFS_DIR/usr/local/bin/crixa-files"
install -m 0755 "$PROJECT_ROOT/apps/crixa-menu.sh" "$ROOTFS_DIR/usr/local/bin/crixa-menu"
install -m 0755 "$PROJECT_ROOT/apps/crixa-wallpaper.sh" "$ROOTFS_DIR/usr/local/bin/crixa-wallpaper"
install -m 0755 "$PROJECT_ROOT/apps/crixa-screenshot.sh" "$ROOTFS_DIR/usr/local/bin/crixa-screenshot"
install -m 0755 "$PROJECT_ROOT/apps/crixa-task-manager.sh" "$ROOTFS_DIR/usr/local/bin/crixa-task-manager"
install -m 0755 "$PROJECT_ROOT/apps/crixa-task-manager.py" "$ROOTFS_DIR/usr/local/bin/crixa-task-manager.py"
install -m 0755 "$PROJECT_ROOT/apps/crixa-fetch.sh" "$ROOTFS_DIR/usr/local/bin/crixa-fetch"
install -m 0755 "$PROJECT_ROOT/apps/neofetch.sh" "$ROOTFS_DIR/usr/local/bin/neofetch"
install -d "$ROOTFS_DIR/usr/local/sbin"
install -m 0755 "$PROJECT_ROOT/apps/crixa-install.sh" "$ROOTFS_DIR/usr/local/sbin/crixa-install"

install -d "$ROOTFS_DIR/usr/share/applications"
install -m 0644 "$PROJECT_ROOT/apps/crixa-settings.desktop" "$ROOTFS_DIR/usr/share/applications/crixa-settings.desktop"
install -m 0644 "$PROJECT_ROOT/apps/crixa-browser.desktop" "$ROOTFS_DIR/usr/share/applications/crixa-browser.desktop"
install -m 0644 "$PROJECT_ROOT/apps/crixa-launcher.desktop" "$ROOTFS_DIR/usr/share/applications/crixa-launcher.desktop"
install -m 0644 "$PROJECT_ROOT/apps/crixa-terminal.desktop" "$ROOTFS_DIR/usr/share/applications/crixa-terminal.desktop"
install -m 0644 "$PROJECT_ROOT/apps/crixa-files.desktop" "$ROOTFS_DIR/usr/share/applications/crixa-files.desktop"
install -m 0644 "$PROJECT_ROOT/apps/crixa-youtube.desktop" "$ROOTFS_DIR/usr/share/applications/crixa-youtube.desktop"
install -m 0644 "$PROJECT_ROOT/apps/crixa-wallpapers.desktop" "$ROOTFS_DIR/usr/share/applications/crixa-wallpapers.desktop"
install -m 0644 "$PROJECT_ROOT/apps/crixa-task-manager.desktop" "$ROOTFS_DIR/usr/share/applications/crixa-task-manager.desktop"
install -m 0644 "$PROJECT_ROOT/apps/crixa-store.desktop" "$ROOTFS_DIR/usr/share/applications/crixa-store.desktop"
install -m 0644 "$PROJECT_ROOT/apps/crixa-installer.desktop" "$ROOTFS_DIR/usr/share/applications/crixa-installer.desktop"
install -m 0644 "$PROJECT_ROOT/apps/crixa-updater.desktop" "$ROOTFS_DIR/usr/share/applications/crixa-updater.desktop"
install -m 0644 "$PROJECT_ROOT/apps/crixa-wayland-control.desktop" "$ROOTFS_DIR/usr/share/applications/crixa-wayland-control.desktop"

install -d "$ROOTFS_DIR/usr/share/wayland-sessions" "$ROOTFS_DIR/usr/share/xsessions"
install -m 0644 "$PROJECT_ROOT/apps/crixa-wayland-session.desktop" "$ROOTFS_DIR/usr/share/wayland-sessions/crixa-wayland.desktop"
install -m 0644 "$PROJECT_ROOT/apps/crixa-wayland-session.desktop" "$ROOTFS_DIR/usr/share/xsessions/crixa-wayland.desktop"

install -d "$ROOTFS_DIR/usr/share/crixa-store"
install -m 0644 "$PROJECT_ROOT/store-packages/catalog.json" "$ROOTFS_DIR/usr/share/crixa-store/catalog.json"
rm -rf "$ROOTFS_DIR/usr/share/crixa-store/packages"
cp -a "$PROJECT_ROOT/store-packages/packages" "$ROOTFS_DIR/usr/share/crixa-store/packages"
install -d "$ROOTFS_DIR/usr/share/crixa-store/backends"
install -m 0644 "$PROJECT_ROOT/store-backends/manifests/crixa-repo.json" "$ROOTFS_DIR/usr/share/crixa-store/backends/crixa-repo.json"
install -m 0644 "$PROJECT_ROOT/store-backends/manifests/flathub.json" "$ROOTFS_DIR/usr/share/crixa-store/backends/flathub.json"
install -d "$ROOTFS_DIR/usr/lib/crixa-store/backends"
install -m 0755 "$PROJECT_ROOT/store-backends/backend-crixa-repo.py" "$ROOTFS_DIR/usr/lib/crixa-store/backends/backend-crixa-repo.py"
install -m 0755 "$PROJECT_ROOT/store-backends/backend-flatpak.py" "$ROOTFS_DIR/usr/lib/crixa-store/backends/backend-flatpak.py"
install -d "$ROOTFS_DIR/usr/share/crixa-store/extensions"
install -m 0644 "$PROJECT_ROOT/store-backends/extensions/README.md" "$ROOTFS_DIR/usr/share/crixa-store/extensions/README.md"
install -m 0755 "$PROJECT_ROOT/store-backends/extensions/example-template.py" "$ROOTFS_DIR/usr/share/crixa-store/extensions/example-template.py"

rm -rf "$ROOTFS_DIR/usr/share/crixa-repo"
install -d "$ROOTFS_DIR/usr/share/crixa-repo"
cp -a "$PROJECT_ROOT/crixa-repo/." "$ROOTFS_DIR/usr/share/crixa-repo"

cat > "$ROOTFS_DIR/etc/crixa-release.json" <<EOF
{
  "product": "CRIXA OS",
  "version": "$CRIXA_VERSION",
  "track": "$CRIXA_TRACK",
  "build_id": "$CRIXA_BUILD_ID"
}
EOF

install -d "$ROOTFS_DIR/etc/skel/.config/openbox"
install -d "$ROOTFS_DIR/etc/skel/.config/tint2"
install -d "$ROOTFS_DIR/etc/skel/.config/rofi"
install -d "$ROOTFS_DIR/etc/skel/.config/gtk-3.0"
install -d "$ROOTFS_DIR/etc/skel/.config/Thunar"
install -d "$ROOTFS_DIR/etc/skel/.config/picom"
install -d "$ROOTFS_DIR/etc/skel/.config/crixa-store/backends"
install -d "$ROOTFS_DIR/etc/skel/.config/labwc"
install -d "$ROOTFS_DIR/etc/skel/.config/waybar"
install -d "$ROOTFS_DIR/etc/skel/.config/wofi"
install -d "$ROOTFS_DIR/etc/X11/xorg.conf.d"
install -m 0644 "$PROJECT_ROOT/ui-shell/rc.xml" "$ROOTFS_DIR/etc/skel/.config/openbox/rc.xml"
install -m 0644 "$PROJECT_ROOT/ui-shell/menu.xml" "$ROOTFS_DIR/etc/skel/.config/openbox/menu.xml"
install -m 0755 "$PROJECT_ROOT/ui-shell/autostart" "$ROOTFS_DIR/etc/skel/.config/openbox/autostart"
install -m 0644 "$PROJECT_ROOT/ui-shell/tint2rc" "$ROOTFS_DIR/etc/skel/.config/tint2/tint2rc"
install -m 0644 "$PROJECT_ROOT/ui-shell/rofi.rasi" "$ROOTFS_DIR/etc/skel/.config/rofi/config.rasi"
install -m 0644 "$PROJECT_ROOT/ui-shell/Xresources" "$ROOTFS_DIR/etc/skel/.Xresources"
install -m 0644 "$PROJECT_ROOT/ui-shell/gtk-settings.ini" "$ROOTFS_DIR/etc/skel/.config/gtk-3.0/settings.ini"
install -m 0644 "$PROJECT_ROOT/ui-shell/thunar-uca.xml" "$ROOTFS_DIR/etc/skel/.config/Thunar/uca.xml"
install -m 0644 "$PROJECT_ROOT/ui-shell/thunarrc" "$ROOTFS_DIR/etc/skel/.config/Thunar/thunarrc"
install -m 0644 "$PROJECT_ROOT/ui-shell/picom.conf" "$ROOTFS_DIR/etc/skel/.config/picom/picom.conf"
install -m 0755 "$PROJECT_ROOT/ui-shell-wayland/labwc/autostart" "$ROOTFS_DIR/etc/skel/.config/labwc/autostart"
install -m 0644 "$PROJECT_ROOT/ui-shell-wayland/labwc/environment" "$ROOTFS_DIR/etc/skel/.config/labwc/environment"
install -m 0644 "$PROJECT_ROOT/ui-shell-wayland/waybar/config" "$ROOTFS_DIR/etc/skel/.config/waybar/config"
install -m 0644 "$PROJECT_ROOT/ui-shell-wayland/waybar/style.css" "$ROOTFS_DIR/etc/skel/.config/waybar/style.css"
install -m 0644 "$PROJECT_ROOT/ui-shell-wayland/wofi/config" "$ROOTFS_DIR/etc/skel/.config/wofi/config"
install -m 0644 "$PROJECT_ROOT/ui-shell-wayland/wofi/style.css" "$ROOTFS_DIR/etc/skel/.config/wofi/style.css"
install -m 0644 "$PROJECT_ROOT/ui-shell/xorg-input.conf" "$ROOTFS_DIR/etc/X11/xorg.conf.d/40-crixa-input.conf"
ensure_bashrc_snippet "$ROOTFS_DIR/etc/skel/.bashrc"

if [[ -d "$ROOTFS_DIR/home/$LIVE_USER" ]]; then
  install -d "$ROOTFS_DIR/home/$LIVE_USER/.config/openbox"
  install -d "$ROOTFS_DIR/home/$LIVE_USER/.config/tint2"
  install -d "$ROOTFS_DIR/home/$LIVE_USER/.config/rofi"
install -d "$ROOTFS_DIR/home/$LIVE_USER/.config/gtk-3.0"
install -d "$ROOTFS_DIR/home/$LIVE_USER/.config/Thunar"
install -d "$ROOTFS_DIR/home/$LIVE_USER/.config/picom"
install -d "$ROOTFS_DIR/home/$LIVE_USER/.config/crixa-store/backends"
install -d "$ROOTFS_DIR/home/$LIVE_USER/.config/labwc"
install -d "$ROOTFS_DIR/home/$LIVE_USER/.config/waybar"
install -d "$ROOTFS_DIR/home/$LIVE_USER/.config/wofi"
  install -m 0644 "$PROJECT_ROOT/ui-shell/rc.xml" "$ROOTFS_DIR/home/$LIVE_USER/.config/openbox/rc.xml"
  install -m 0644 "$PROJECT_ROOT/ui-shell/menu.xml" "$ROOTFS_DIR/home/$LIVE_USER/.config/openbox/menu.xml"
  install -m 0755 "$PROJECT_ROOT/ui-shell/autostart" "$ROOTFS_DIR/home/$LIVE_USER/.config/openbox/autostart"
  install -m 0644 "$PROJECT_ROOT/ui-shell/tint2rc" "$ROOTFS_DIR/home/$LIVE_USER/.config/tint2/tint2rc"
  install -m 0644 "$PROJECT_ROOT/ui-shell/rofi.rasi" "$ROOTFS_DIR/home/$LIVE_USER/.config/rofi/config.rasi"
  install -m 0644 "$PROJECT_ROOT/ui-shell/Xresources" "$ROOTFS_DIR/home/$LIVE_USER/.Xresources"
  install -m 0644 "$PROJECT_ROOT/ui-shell/gtk-settings.ini" "$ROOTFS_DIR/home/$LIVE_USER/.config/gtk-3.0/settings.ini"
  install -m 0644 "$PROJECT_ROOT/ui-shell/thunar-uca.xml" "$ROOTFS_DIR/home/$LIVE_USER/.config/Thunar/uca.xml"
  install -m 0644 "$PROJECT_ROOT/ui-shell/thunarrc" "$ROOTFS_DIR/home/$LIVE_USER/.config/Thunar/thunarrc"
  install -m 0644 "$PROJECT_ROOT/ui-shell/picom.conf" "$ROOTFS_DIR/home/$LIVE_USER/.config/picom/picom.conf"
  install -m 0755 "$PROJECT_ROOT/ui-shell-wayland/labwc/autostart" "$ROOTFS_DIR/home/$LIVE_USER/.config/labwc/autostart"
  install -m 0644 "$PROJECT_ROOT/ui-shell-wayland/labwc/environment" "$ROOTFS_DIR/home/$LIVE_USER/.config/labwc/environment"
  install -m 0644 "$PROJECT_ROOT/ui-shell-wayland/waybar/config" "$ROOTFS_DIR/home/$LIVE_USER/.config/waybar/config"
  install -m 0644 "$PROJECT_ROOT/ui-shell-wayland/waybar/style.css" "$ROOTFS_DIR/home/$LIVE_USER/.config/waybar/style.css"
  install -m 0644 "$PROJECT_ROOT/ui-shell-wayland/wofi/config" "$ROOTFS_DIR/home/$LIVE_USER/.config/wofi/config"
  install -m 0644 "$PROJECT_ROOT/ui-shell-wayland/wofi/style.css" "$ROOTFS_DIR/home/$LIVE_USER/.config/wofi/style.css"
  ensure_bashrc_snippet "$ROOTFS_DIR/home/$LIVE_USER/.bashrc"

  if [[ "$(id -u)" -eq 0 ]]; then
    chroot "$ROOTFS_DIR" /bin/bash -lc "chown -R $LIVE_USER:$LIVE_USER /home/$LIVE_USER/.config /home/$LIVE_USER/.Xresources"
  fi
fi

if [[ "$(id -u)" -eq 0 && "$SYNC_ENABLE_APT" == "1" ]]; then
  mount_chroot_filesystems

  chroot_apt_update() {
    if chroot "$ROOTFS_DIR" /bin/bash -lc "apt-get update"; then
      return 0
    fi
    echo "Signed apt update failed inside project rootfs; retrying with insecure mirror mode (WSL NTFS perms workaround)"
    chroot "$ROOTFS_DIR" /bin/bash -lc "apt-get -o Acquire::AllowInsecureRepositories=true -o Acquire::AllowDowngradeToInsecureRepositories=true update"
  }

  chroot_apt_install() {
    local pkg_args=("$@")
    if chroot "$ROOTFS_DIR" /bin/bash -lc "DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends ${pkg_args[*]}"; then
      return 0
    fi
    echo "Signed package install failed for: ${pkg_args[*]}"
    echo "Retrying package install in insecure mode (WSL NTFS perms workaround)"
    chroot "$ROOTFS_DIR" /bin/bash -lc "DEBIAN_FRONTEND=noninteractive apt-get -o Acquire::AllowInsecureRepositories=true -o Acquire::AllowDowngradeToInsecureRepositories=true --allow-unauthenticated install -y --no-install-recommends ${pkg_args[*]}"
  }

  cat > "$ROOTFS_DIR/etc/apt/sources.list" <<EOF
deb $MIRROR $DIST main contrib non-free non-free-firmware
deb https://security.debian.org/debian-security $DIST-security main contrib non-free non-free-firmware
deb $MIRROR $DIST-updates main contrib non-free non-free-firmware
EOF

  # Recover from partial installs before attempting package deltas.
  chroot "$ROOTFS_DIR" /bin/bash -lc "DEBIAN_FRONTEND=noninteractive dpkg --configure -a || true"
  chroot "$ROOTFS_DIR" /bin/bash -lc "DEBIAN_FRONTEND=noninteractive apt-get -f install -y || true"

  REQUIRED_HW_PKGS=(
    firefox-esr
    python3-tk
    linux-headers-amd64
    dkms
    firmware-linux
    firmware-linux-nonfree
    firmware-amd-graphics
    nvidia-driver
    nvidia-vulkan-icd
    nvidia-smi
    nvidia-settings
    firmware-nvidia-gsp
    network-manager
    network-manager-gnome
    wpasupplicant
    iw
    rfkill
    modemmanager
    usb-modeswitch
    bluez
    blueman
    pipewire
    pipewire-pulse
    wireplumber
    libspa-0.2-bluetooth
    alsa-utils
    pulseaudio-utils
    pavucontrol
    mesa-utils
    libgl1-mesa-dri
    mesa-vulkan-drivers
    maim
    scrot
    xclip
    wl-clipboard
    grim
    slurp
    libnotify-bin
    xserver-xorg-video-all
    xserver-xorg-input-all
    pciutils
    usbutils
    dmidecode
  )
  OPTIONAL_HW_PKGS=(
    firmware-linux-free
    firmware-realtek
    firmware-iwlwifi
    firmware-atheros
    firmware-brcm80211
    firmware-misc-nonfree
    intel-microcode
    amd64-microcode
    vulkan-tools
    mesa-va-drivers
    mesa-vdpau-drivers
    intel-media-va-driver-non-free
    va-driver-all
    nvidia-detect
  )

  missing_required=()
  for pkg in "${REQUIRED_HW_PKGS[@]}"; do
    if ! chroot "$ROOTFS_DIR" /bin/bash -lc "dpkg -s '$pkg' >/dev/null 2>&1"; then
      missing_required+=("$pkg")
    fi
  done

  missing_optional=()
  for pkg in "${OPTIONAL_HW_PKGS[@]}"; do
    if ! chroot "$ROOTFS_DIR" /bin/bash -lc "dpkg -s '$pkg' >/dev/null 2>&1"; then
      missing_optional+=("$pkg")
    fi
  done

  if [[ "${#missing_required[@]}" -gt 0 || "${#missing_optional[@]}" -gt 0 ]]; then
    echo "Installing bare-metal hardware stack packages in rootfs"
    chroot_apt_update
    if [[ "${#missing_required[@]}" -gt 0 ]]; then
      chroot_apt_install "${missing_required[@]}"
    fi
    for pkg in "${missing_optional[@]}"; do
      chroot_apt_install "$pkg" || true
    done
  fi
  chroot "$ROOTFS_DIR" /bin/bash -lc "DEBIAN_FRONTEND=noninteractive dpkg --configure -a || true"
  chroot "$ROOTFS_DIR" /bin/bash -lc "DEBIAN_FRONTEND=noninteractive apt-get -f install -y || true"

  if ! chroot "$ROOTFS_DIR" /bin/bash -lc "dpkg -s grub-common grub2-common grub-pc-bin grub-efi-amd64-bin >/dev/null 2>&1"; then
    echo "Installer runtime packages missing in rootfs; installing required dependencies"
    chroot_apt_update
    chroot_apt_install grub-common grub2-common grub-pc-bin grub-efi-amd64-bin rsync parted gdisk dosfstools e2fsprogs
  fi
  if ! chroot "$ROOTFS_DIR" /bin/bash -lc "command -v flatpak >/dev/null 2>&1"; then
    echo "Flatpak runtime missing in rootfs; installing"
    chroot_apt_update || true
    chroot_apt_install flatpak xdg-desktop-portal xdg-desktop-portal-gtk || true
    chroot "$ROOTFS_DIR" /bin/bash -lc "apt-get clean || true"
  fi
  if chroot "$ROOTFS_DIR" /bin/bash -lc "test -r /proc/sys/kernel/random/boot_id"; then
    chroot "$ROOTFS_DIR" /bin/bash -lc "flatpak --system remote-add --if-not-exists flathub https://dl.flathub.org/repo/flathub.flatpakrepo || true"
  else
    echo "Skipping system flatpak remote-add in sync mode (no /proc inside chroot)"
  fi
  if ! chroot "$ROOTFS_DIR" /bin/bash -lc "command -v weston >/dev/null 2>&1"; then
    echo "Wayland preview packages missing in rootfs; attempting best-effort install"
    chroot_apt_update || true
    for pkg in weston xwayland swaybg waybar wofi foot; do
      chroot_apt_install "$pkg" || true
    done
  fi
  chroot "$ROOTFS_DIR" /bin/bash -lc "apt-get clean || true"
  chroot "$ROOTFS_DIR" /bin/bash -lc "systemctl disable apt-daily.timer apt-daily-upgrade.timer man-db.timer e2scrub_all.timer fstrim.timer NetworkManager-wait-online.service || true"
  chroot "$ROOTFS_DIR" /bin/bash -lc "systemctl enable NetworkManager bluetooth ModemManager || true"
  chroot "$ROOTFS_DIR" /bin/bash -lc "update-desktop-database /usr/share/applications || true"
  chroot "$ROOTFS_DIR" /bin/bash -lc "gtk-update-icon-cache -f /usr/share/icons/hicolor || true"
fi

echo "Synced project assets into $ROOTFS_DIR"
