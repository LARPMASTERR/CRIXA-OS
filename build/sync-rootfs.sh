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

require_file "$PROJECT_ROOT/ui-shell/gtk-settings.ini"
require_file "$PROJECT_ROOT/ui-shell/xorg-input.conf"
require_file "$PROJECT_ROOT/themes/CRIXA/gtk.css"
require_file "$PROJECT_ROOT/themes/CRIXA/index.theme"
require_file "$PROJECT_ROOT/ui-shell/bashrc-crixa-snippet"
require_file "$PROJECT_ROOT/apps/crixa-fetch.sh"
require_file "$PROJECT_ROOT/apps/crixa-shell-bootstrap.sh"
require_file "$PROJECT_ROOT/apps/fastfetch.sh"
require_file "$PROJECT_ROOT/apps/crixa-screenshot.sh"
require_file "$PROJECT_ROOT/apps/neofetch.sh"
require_file "$PROJECT_ROOT/apps/crixapkg.sh"
require_file "$PROJECT_ROOT/apps/crixapkg.py"
require_file "$PROJECT_ROOT/apps/crixa-settings.py"
require_file "$PROJECT_ROOT/apps/crixa-welcome.sh"
require_file "$PROJECT_ROOT/apps/crixa-welcome.py"
require_file "$PROJECT_ROOT/apps/crixa-welcome.desktop"
require_file "$PROJECT_ROOT/apps/crixa-dashboard.py"
require_file "$PROJECT_ROOT/apps/crixa-store.py"
require_file "$PROJECT_ROOT/apps/crixa-store.sh"
require_file "$PROJECT_ROOT/apps/crixa-store.desktop"
require_file "$PROJECT_ROOT/apps/crixa-installer.sh"
require_file "$PROJECT_ROOT/apps/crixa-installer.py"
require_file "$PROJECT_ROOT/apps/crixa-installer-helper.py"
require_file "$PROJECT_ROOT/apps/org.crixa.dockyard.policy"
require_file "$PROJECT_ROOT/apps/crixa-install.sh"
require_file "$PROJECT_ROOT/apps/crixa-installer.desktop"
require_file "$PROJECT_ROOT/apps/crixa-updater.sh"
require_file "$PROJECT_ROOT/apps/crixa-updater.py"
require_file "$PROJECT_ROOT/apps/crixa-updater-helper.py"
require_file "$PROJECT_ROOT/apps/org.crixa.transit.policy"
require_file "$PROJECT_ROOT/apps/crixa-updater.desktop"
require_file "$PROJECT_ROOT/apps/crixa-session-mode.sh"
require_file "$PROJECT_ROOT/apps/crixa-wayland-control.sh"
require_file "$PROJECT_ROOT/apps/crixa-wayland-control.py"
require_file "$PROJECT_ROOT/apps/crixa-wayland-control.desktop"
require_file "$PROJECT_ROOT/apps/crixa-releasectl.sh"
require_file "$PROJECT_ROOT/apps/crixa-releasectl.py"
require_file "$PROJECT_ROOT/apps/crixa-task-manager.sh"
require_file "$PROJECT_ROOT/apps/crixa-task-manager.py"
require_file "$PROJECT_ROOT/apps/crixa-task-manager-helper.py"
require_file "$PROJECT_ROOT/apps/org.crixa.pulse.policy"
require_file "$PROJECT_ROOT/store-backends/backend-crixa-repo.py"
require_file "$PROJECT_ROOT/store-backends/backend-flatpak.py"
require_file "$PROJECT_ROOT/store-backends/crixa-store-system-helper.py"
require_file "$PROJECT_ROOT/store-backends/org.crixa.store.policy"
require_file "$PROJECT_ROOT/store-backends/manifests/crixa-repo.json"
require_file "$PROJECT_ROOT/store-backends/manifests/flathub.json"
require_file "$PROJECT_ROOT/store-backends/extensions/README.md"
require_file "$PROJECT_ROOT/store-backends/extensions/example-template.py"
require_file "$PROJECT_ROOT/build/build-crixa-repo.sh"
require_file "$PROJECT_ROOT/store-packages/catalog.json"
require_file "$PROJECT_ROOT/store-packages/assets/README.md"
require_file "$PROJECT_ROOT/store-packages/system-rollouts.json"
require_file "$PROJECT_ROOT/store-packages/packages/lumen-notes/payload/bin/lumen-notes"
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
require_file "$PROJECT_ROOT/Wallpapers/DefaultWP.jpeg"
require_file "$PROJECT_ROOT/assets/wallpapers/crixa-wallpaper-mist-mountains.jpg"
require_file "$PROJECT_ROOT/assets/wallpapers/crixa-wallpaper-sand-ridges.jpg"
require_file "$PROJECT_ROOT/assets/wallpapers/crixa-wallpaper-cloud-coast.jpg"
require_file "$PROJECT_ROOT/assets/wallpapers/crixa-wallpaper-fog-ocean.jpg"
require_file "$PROJECT_ROOT/assets/wallpapers/crixa-wallpaper-snow-quiet.jpg"
require_file "$PROJECT_ROOT/plasma-shell/icon-theme/CRIXA-Depth/index.theme"
require_file "$PROJECT_ROOT/plasma-shell/look-and-feel/org.crixa.shell.desktop/metadata.json"
require_file "$PROJECT_ROOT/plasma-shell/look-and-feel/org.crixa.shell.desktop/contents/defaults"
require_file "$PROJECT_ROOT/plasma-shell/look-and-feel/org.crixa.shell.desktop/contents/layouts/org.kde.plasma.desktop-layout.js"
require_file "$PROJECT_ROOT/plasma-shell/desktoptheme/CRIXA-Material/metadata.json"
require_file "$PROJECT_ROOT/plasma-shell/desktoptheme/CRIXA-Material/plasmarc"
require_file "$PROJECT_ROOT/plasma-shell/desktoptheme/CRIXA-Material/widgets/panel-background.svg"
require_file "$PROJECT_ROOT/plasma-shell/desktoptheme/CRIXA-Material/widgets/surface-solid.svg"
require_file "$PROJECT_ROOT/plasma-shell/desktoptheme/CRIXA-Material/widgets/surface-translucent.svg"
require_file "$PROJECT_ROOT/plasma-shell/desktoptheme/CRIXA-Material/widgets/tasks.svg"
require_file "$PROJECT_ROOT/plasma-shell/color-schemes/CrixaShell.colors"
require_file "$PROJECT_ROOT/plasma-shell/config/kdedefaults/package"
require_file "$PROJECT_ROOT/plasma-shell/config/kdedefaults/kdeglobals"
require_file "$PROJECT_ROOT/plasma-shell/config/kdedefaults/plasmarc"
require_file "$PROJECT_ROOT/plasma-shell/config/kdedefaults/kwinrc"
require_file "$PROJECT_ROOT/plasma-shell/config/kdedefaults/kcminputrc"
require_file "$PROJECT_ROOT/plasma-shell/config/kdedefaults/ksplashrc"
require_file "$PROJECT_ROOT/plasma-shell/autostart/crixa-shell-bootstrap.desktop"
require_file "$PROJECT_ROOT/plasma-shell/autostart/crixa-welcome.desktop"
require_file "$PROJECT_ROOT/plasma-shell/sddm/theme.conf.user"

for package_dir in "$PROJECT_ROOT"/store-packages/packages/*; do
  [[ -d "$package_dir" ]] || continue
  package_id="$(basename "$package_dir")"
  require_file "$package_dir/payload/bin/$package_id"
  require_file "$package_dir/payload/applications/$package_id.desktop"
  require_file "$package_dir/payload/icons/hicolor/scalable/apps/$package_id.svg"
done

chmod +x "$PROJECT_ROOT/build/build-crixa-repo.sh"
"$PROJECT_ROOT/build/build-crixa-repo.sh"
require_file "$PROJECT_ROOT/crixa-repo/metadata/repo.json"
require_file "$PROJECT_ROOT/crixa-repo/metadata/repo.sig"
require_file "$PROJECT_ROOT/crixa-repo/metadata/system-updates.json"
require_file "$PROJECT_ROOT/crixa-repo/metadata/system-updates.sig"
require_file "$PROJECT_ROOT/crixa-repo/keys/repo-public.pem"

install -d "$ROOTFS_DIR/usr/share/themes/CRIXA/gtk-3.0"
install -m 0644 "$PROJECT_ROOT/themes/CRIXA/gtk.css" "$ROOTFS_DIR/usr/share/themes/CRIXA/gtk-3.0/gtk.css"
install -m 0644 "$PROJECT_ROOT/themes/CRIXA/index.theme" "$ROOTFS_DIR/usr/share/themes/CRIXA/index.theme"

install -d "$ROOTFS_DIR/usr/share/backgrounds"
install -d "$ROOTFS_DIR/usr/share/backgrounds/crixa"
install -m 0644 "$PROJECT_ROOT/Wallpapers/DefaultWP.jpeg" "$ROOTFS_DIR/usr/share/backgrounds/crixa-wallpaper.jpg"
install -m 0644 "$PROJECT_ROOT/assets/wallpapers/crixa-wallpaper.svg" "$ROOTFS_DIR/usr/share/backgrounds/crixa-wallpaper.svg"
install -m 0644 "$PROJECT_ROOT/Wallpapers/DefaultWP.jpeg" "$ROOTFS_DIR/usr/share/backgrounds/crixa/00-defaultwp.jpg"
install -m 0644 "$PROJECT_ROOT/assets/wallpapers/crixa-wallpaper-mist-mountains.jpg" "$ROOTFS_DIR/usr/share/backgrounds/crixa/10-mist-mountains.jpg"
install -m 0644 "$PROJECT_ROOT/assets/wallpapers/crixa-wallpaper-sand-ridges.jpg" "$ROOTFS_DIR/usr/share/backgrounds/crixa/20-sand-ridges.jpg"
install -m 0644 "$PROJECT_ROOT/assets/wallpapers/crixa-wallpaper-cloud-coast.jpg" "$ROOTFS_DIR/usr/share/backgrounds/crixa/30-cloud-coast.jpg"
install -m 0644 "$PROJECT_ROOT/assets/wallpapers/crixa-wallpaper-fog-ocean.jpg" "$ROOTFS_DIR/usr/share/backgrounds/crixa/40-fog-ocean.jpg"
install -m 0644 "$PROJECT_ROOT/assets/wallpapers/crixa-wallpaper-snow-quiet.jpg" "$ROOTFS_DIR/usr/share/backgrounds/crixa/50-snow-quiet.jpg"

install -d "$ROOTFS_DIR/usr/share/plasma/look-and-feel/org.crixa.shell.desktop/contents/layouts"
install -m 0644 "$PROJECT_ROOT/plasma-shell/look-and-feel/org.crixa.shell.desktop/metadata.json" "$ROOTFS_DIR/usr/share/plasma/look-and-feel/org.crixa.shell.desktop/metadata.json"
install -m 0644 "$PROJECT_ROOT/plasma-shell/look-and-feel/org.crixa.shell.desktop/contents/defaults" "$ROOTFS_DIR/usr/share/plasma/look-and-feel/org.crixa.shell.desktop/contents/defaults"
install -m 0644 "$PROJECT_ROOT/plasma-shell/look-and-feel/org.crixa.shell.desktop/contents/layouts/org.kde.plasma.desktop-layout.js" "$ROOTFS_DIR/usr/share/plasma/look-and-feel/org.crixa.shell.desktop/contents/layouts/org.kde.plasma.desktop-layout.js"
install -d "$ROOTFS_DIR/usr/share/plasma/desktoptheme/crixa-material/widgets"
install -d "$ROOTFS_DIR/usr/share/plasma/desktoptheme/crixa-material/dialogs"
install -m 0644 "$PROJECT_ROOT/plasma-shell/desktoptheme/CRIXA-Material/metadata.json" "$ROOTFS_DIR/usr/share/plasma/desktoptheme/crixa-material/metadata.json"
install -m 0644 "$PROJECT_ROOT/plasma-shell/desktoptheme/CRIXA-Material/plasmarc" "$ROOTFS_DIR/usr/share/plasma/desktoptheme/crixa-material/plasmarc"
install -m 0644 "$PROJECT_ROOT/plasma-shell/desktoptheme/CRIXA-Material/widgets/panel-background.svg" "$ROOTFS_DIR/usr/share/plasma/desktoptheme/crixa-material/widgets/panel-background.svg"
install -m 0644 "$PROJECT_ROOT/plasma-shell/desktoptheme/CRIXA-Material/widgets/surface-solid.svg" "$ROOTFS_DIR/usr/share/plasma/desktoptheme/crixa-material/widgets/background.svg"
install -m 0644 "$PROJECT_ROOT/plasma-shell/desktoptheme/CRIXA-Material/widgets/surface-solid.svg" "$ROOTFS_DIR/usr/share/plasma/desktoptheme/crixa-material/dialogs/background.svg"
install -m 0644 "$PROJECT_ROOT/plasma-shell/desktoptheme/CRIXA-Material/widgets/surface-translucent.svg" "$ROOTFS_DIR/usr/share/plasma/desktoptheme/crixa-material/widgets/translucentbackground.svg"
install -m 0644 "$PROJECT_ROOT/plasma-shell/desktoptheme/CRIXA-Material/widgets/surface-translucent.svg" "$ROOTFS_DIR/usr/share/plasma/desktoptheme/crixa-material/widgets/tooltip.svg"
install -m 0644 "$PROJECT_ROOT/plasma-shell/desktoptheme/CRIXA-Material/widgets/tasks.svg" "$ROOTFS_DIR/usr/share/plasma/desktoptheme/crixa-material/widgets/tasks.svg"

install -d "$ROOTFS_DIR/usr/share/color-schemes"
install -m 0644 "$PROJECT_ROOT/plasma-shell/color-schemes/CrixaShell.colors" "$ROOTFS_DIR/usr/share/color-schemes/CrixaShell.colors"

install -m 0644 "$PROJECT_ROOT/plasma-shell/sddm/theme.conf.user" "$ROOTFS_DIR/usr/share/sddm/themes/breeze/theme.conf.user"

install -d "$ROOTFS_DIR/usr/share/icons/hicolor/scalable/apps"
install -d "$ROOTFS_DIR/usr/share/icons/CRIXA-Depth/scalable/apps"
install -m 0644 "$PROJECT_ROOT/plasma-shell/icon-theme/CRIXA-Depth/index.theme" "$ROOTFS_DIR/usr/share/icons/CRIXA-Depth/index.theme"
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
for icon_path in "$PROJECT_ROOT"/assets/icons/crixa-*.svg; do
  install -m 0644 "$icon_path" "$ROOTFS_DIR/usr/share/icons/CRIXA-Depth/scalable/apps/$(basename "$icon_path")"
done

install -d "$ROOTFS_DIR/usr/local/bin"
install -m 0755 "$PROJECT_ROOT/apps/crixa-settings.sh" "$ROOTFS_DIR/usr/local/bin/crixa-settings"
install -m 0755 "$PROJECT_ROOT/apps/crixa-settings.py" "$ROOTFS_DIR/usr/local/bin/crixa-settings.py"
install -m 0755 "$PROJECT_ROOT/apps/crixa-welcome.sh" "$ROOTFS_DIR/usr/local/bin/crixa-welcome"
install -m 0755 "$PROJECT_ROOT/apps/crixa-welcome.py" "$ROOTFS_DIR/usr/local/bin/crixa-welcome.py"
install -m 0755 "$PROJECT_ROOT/apps/crixa-store.sh" "$ROOTFS_DIR/usr/local/bin/crixa-store"
install -m 0755 "$PROJECT_ROOT/apps/crixa-store.py" "$ROOTFS_DIR/usr/local/bin/crixa-store.py"
install -m 0755 "$PROJECT_ROOT/apps/crixa-installer.sh" "$ROOTFS_DIR/usr/local/bin/crixa-installer"
install -m 0755 "$PROJECT_ROOT/apps/crixa-installer.py" "$ROOTFS_DIR/usr/local/bin/crixa-installer.py"
install -d "$ROOTFS_DIR/usr/lib/crixa-installer"
install -m 0755 "$PROJECT_ROOT/apps/crixa-installer-helper.py" "$ROOTFS_DIR/usr/lib/crixa-installer/crixa-installer-helper.py"
install -d "$ROOTFS_DIR/usr/share/polkit-1/actions"
install -m 0644 "$PROJECT_ROOT/apps/org.crixa.dockyard.policy" "$ROOTFS_DIR/usr/share/polkit-1/actions/org.crixa.dockyard.policy"
install -m 0755 "$PROJECT_ROOT/apps/crixa-updater.sh" "$ROOTFS_DIR/usr/local/bin/crixa-updater"
install -m 0755 "$PROJECT_ROOT/apps/crixa-updater.py" "$ROOTFS_DIR/usr/local/bin/crixa-updater.py"
install -d "$ROOTFS_DIR/usr/lib/crixa-updater"
install -m 0755 "$PROJECT_ROOT/apps/crixa-updater-helper.py" "$ROOTFS_DIR/usr/lib/crixa-updater/crixa-updater-helper.py"
install -d "$ROOTFS_DIR/usr/share/polkit-1/actions"
install -m 0644 "$PROJECT_ROOT/apps/org.crixa.transit.policy" "$ROOTFS_DIR/usr/share/polkit-1/actions/org.crixa.transit.policy"
install -m 0755 "$PROJECT_ROOT/apps/crixa-session-mode.sh" "$ROOTFS_DIR/usr/local/bin/crixa-session-mode"
install -m 0755 "$PROJECT_ROOT/apps/crixa-wayland-control.sh" "$ROOTFS_DIR/usr/local/bin/crixa-wayland-control"
install -m 0755 "$PROJECT_ROOT/apps/crixa-wayland-control.py" "$ROOTFS_DIR/usr/local/bin/crixa-wayland-control.py"
install -m 0755 "$PROJECT_ROOT/apps/crixa-releasectl.sh" "$ROOTFS_DIR/usr/local/bin/crixa-releasectl"
install -m 0755 "$PROJECT_ROOT/apps/crixa-releasectl.py" "$ROOTFS_DIR/usr/local/bin/crixa-releasectl.py"
install -m 0755 "$PROJECT_ROOT/apps/crixapkg.sh" "$ROOTFS_DIR/usr/local/bin/crixapkg"
install -m 0755 "$PROJECT_ROOT/apps/crixapkg.py" "$ROOTFS_DIR/usr/local/bin/crixapkg.py"
install -m 0755 "$PROJECT_ROOT/apps/crixa-browser.sh" "$ROOTFS_DIR/usr/local/bin/crixa-browser"
install -m 0755 "$PROJECT_ROOT/apps/crixa-dashboard.py" "$ROOTFS_DIR/usr/local/bin/crixa-dashboard"
install -m 0755 "$PROJECT_ROOT/apps/crixa-terminal.sh" "$ROOTFS_DIR/usr/local/bin/crixa-terminal"
install -m 0755 "$PROJECT_ROOT/apps/crixa-files.sh" "$ROOTFS_DIR/usr/local/bin/crixa-files"
install -m 0755 "$PROJECT_ROOT/apps/crixa-menu.sh" "$ROOTFS_DIR/usr/local/bin/crixa-menu"
install -m 0755 "$PROJECT_ROOT/apps/crixa-wallpaper.sh" "$ROOTFS_DIR/usr/local/bin/crixa-wallpaper"
install -m 0755 "$PROJECT_ROOT/apps/crixa-screenshot.sh" "$ROOTFS_DIR/usr/local/bin/crixa-screenshot"
install -m 0755 "$PROJECT_ROOT/apps/crixa-task-manager.sh" "$ROOTFS_DIR/usr/local/bin/crixa-task-manager"
install -m 0755 "$PROJECT_ROOT/apps/crixa-task-manager.py" "$ROOTFS_DIR/usr/local/bin/crixa-task-manager.py"
install -d "$ROOTFS_DIR/usr/lib/crixa-task-manager"
install -m 0755 "$PROJECT_ROOT/apps/crixa-task-manager-helper.py" "$ROOTFS_DIR/usr/lib/crixa-task-manager/crixa-task-manager-helper.py"
install -d "$ROOTFS_DIR/usr/share/polkit-1/actions"
install -m 0644 "$PROJECT_ROOT/apps/org.crixa.pulse.policy" "$ROOTFS_DIR/usr/share/polkit-1/actions/org.crixa.pulse.policy"
install -m 0755 "$PROJECT_ROOT/apps/crixa-fetch.sh" "$ROOTFS_DIR/usr/local/bin/crixa-fetch"
install -m 0755 "$PROJECT_ROOT/apps/crixa-shell-bootstrap.sh" "$ROOTFS_DIR/usr/local/bin/crixa-shell-bootstrap"
install -m 0755 "$PROJECT_ROOT/apps/fastfetch.sh" "$ROOTFS_DIR/usr/local/bin/fastfetch"
install -m 0755 "$PROJECT_ROOT/apps/neofetch.sh" "$ROOTFS_DIR/usr/local/bin/neofetch"
install -d "$ROOTFS_DIR/usr/local/sbin"
install -m 0755 "$PROJECT_ROOT/apps/crixa-install.sh" "$ROOTFS_DIR/usr/local/sbin/crixa-install"

install -d "$ROOTFS_DIR/usr/share/applications"
install -m 0644 "$PROJECT_ROOT/apps/crixa-settings.desktop" "$ROOTFS_DIR/usr/share/applications/crixa-settings.desktop"
install -m 0644 "$PROJECT_ROOT/apps/crixa-welcome.desktop" "$ROOTFS_DIR/usr/share/applications/crixa-welcome.desktop"
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
rm -f "$ROOTFS_DIR/usr/local/bin/crixa-wayland-session"
rm -f "$ROOTFS_DIR/usr/share/wayland-sessions/crixa-wayland.desktop" "$ROOTFS_DIR/usr/share/xsessions/crixa-wayland.desktop"

install -d "$ROOTFS_DIR/usr/share/crixa-store"
install -m 0644 "$PROJECT_ROOT/store-packages/catalog.json" "$ROOTFS_DIR/usr/share/crixa-store/catalog.json"
rm -rf "$ROOTFS_DIR/usr/share/crixa-store/packages"
cp -a "$PROJECT_ROOT/store-packages/packages" "$ROOTFS_DIR/usr/share/crixa-store/packages"
rm -rf "$ROOTFS_DIR/usr/share/crixa-store/assets"
cp -a "$PROJECT_ROOT/store-packages/assets" "$ROOTFS_DIR/usr/share/crixa-store/assets"
install -d "$ROOTFS_DIR/usr/share/crixa-store/backends"
install -m 0644 "$PROJECT_ROOT/store-backends/manifests/crixa-repo.json" "$ROOTFS_DIR/usr/share/crixa-store/backends/crixa-repo.json"
install -m 0644 "$PROJECT_ROOT/store-backends/manifests/flathub.json" "$ROOTFS_DIR/usr/share/crixa-store/backends/flathub.json"
install -d "$ROOTFS_DIR/usr/lib/crixa-store/backends"
install -m 0755 "$PROJECT_ROOT/store-backends/backend-crixa-repo.py" "$ROOTFS_DIR/usr/lib/crixa-store/backends/backend-crixa-repo.py"
install -m 0755 "$PROJECT_ROOT/store-backends/backend-flatpak.py" "$ROOTFS_DIR/usr/lib/crixa-store/backends/backend-flatpak.py"
install -d "$ROOTFS_DIR/usr/lib/crixa-store"
install -m 0755 "$PROJECT_ROOT/store-backends/crixa-store-system-helper.py" "$ROOTFS_DIR/usr/lib/crixa-store/crixa-store-system-helper.py"
install -d "$ROOTFS_DIR/usr/share/polkit-1/actions"
install -m 0644 "$PROJECT_ROOT/store-backends/org.crixa.store.policy" "$ROOTFS_DIR/usr/share/polkit-1/actions/org.crixa.store.policy"
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

install -d "$ROOTFS_DIR/etc/skel/.config/gtk-3.0"
install -d "$ROOTFS_DIR/etc/skel/.config/kdedefaults"
install -d "$ROOTFS_DIR/etc/skel/.config/crixa-store/backends"
install -d "$ROOTFS_DIR/etc/sddm.conf.d"
install -d "$ROOTFS_DIR/etc/xdg/autostart"
install -d "$ROOTFS_DIR/etc/X11/xorg.conf.d"

cat > "$ROOTFS_DIR/etc/sddm.conf.d/10-crixa.conf" <<EOF
[General]
DisplayServer=x11

[Theme]
Current=breeze
CursorTheme=breeze_cursors
EnableAvatars=false

[Users]
RememberLastSession=false
RememberLastUser=false
EOF

cat > "$ROOTFS_DIR/etc/sddm.conf.d/20-crixa-autologin.conf" <<EOF
[Autologin]
User=$LIVE_USER
Session=plasma.desktop
Relogin=false
EOF

rm -f "$ROOTFS_DIR/etc/lightdm/lightdm.conf.d/50-crixa-autologin.conf"
rm -rf \
  "$ROOTFS_DIR/etc/skel/.config/openbox" \
  "$ROOTFS_DIR/etc/skel/.config/tint2" \
  "$ROOTFS_DIR/etc/skel/.config/rofi" \
  "$ROOTFS_DIR/etc/skel/.config/Thunar" \
  "$ROOTFS_DIR/etc/skel/.config/picom" \
  "$ROOTFS_DIR/etc/skel/.config/labwc" \
  "$ROOTFS_DIR/etc/skel/.config/waybar" \
  "$ROOTFS_DIR/etc/skel/.config/wofi" \
  "$ROOTFS_DIR/usr/share/themes/CRIXA/openbox-3"
rm -f "$ROOTFS_DIR/etc/skel/.bash_profile" "$ROOTFS_DIR/etc/skel/.xinitrc" "$ROOTFS_DIR/etc/skel/.Xresources"
install -m 0644 "$PROJECT_ROOT/ui-shell/gtk-settings.ini" "$ROOTFS_DIR/etc/skel/.config/gtk-3.0/settings.ini"
install -m 0644 "$PROJECT_ROOT/plasma-shell/config/kdedefaults/package" "$ROOTFS_DIR/etc/skel/.config/kdedefaults/package"
install -m 0644 "$PROJECT_ROOT/plasma-shell/config/kdedefaults/kdeglobals" "$ROOTFS_DIR/etc/skel/.config/kdedefaults/kdeglobals"
install -m 0644 "$PROJECT_ROOT/plasma-shell/config/kdedefaults/plasmarc" "$ROOTFS_DIR/etc/skel/.config/kdedefaults/plasmarc"
install -m 0644 "$PROJECT_ROOT/plasma-shell/config/kdedefaults/kwinrc" "$ROOTFS_DIR/etc/skel/.config/kdedefaults/kwinrc"
install -m 0644 "$PROJECT_ROOT/plasma-shell/config/kdedefaults/kcminputrc" "$ROOTFS_DIR/etc/skel/.config/kdedefaults/kcminputrc"
install -m 0644 "$PROJECT_ROOT/plasma-shell/config/kdedefaults/ksplashrc" "$ROOTFS_DIR/etc/skel/.config/kdedefaults/ksplashrc"
install -m 0644 "$PROJECT_ROOT/plasma-shell/autostart/crixa-shell-bootstrap.desktop" "$ROOTFS_DIR/etc/xdg/autostart/crixa-shell-bootstrap.desktop"
install -m 0644 "$PROJECT_ROOT/plasma-shell/autostart/crixa-welcome.desktop" "$ROOTFS_DIR/etc/xdg/autostart/crixa-welcome.desktop"
install -m 0644 "$PROJECT_ROOT/ui-shell/xorg-input.conf" "$ROOTFS_DIR/etc/X11/xorg.conf.d/40-crixa-input.conf"
ensure_bashrc_snippet "$ROOTFS_DIR/etc/skel/.bashrc"

if [[ -d "$ROOTFS_DIR/home/$LIVE_USER" ]]; then
  install -d "$ROOTFS_DIR/home/$LIVE_USER/.config/gtk-3.0"
  install -d "$ROOTFS_DIR/home/$LIVE_USER/.config/kdedefaults"
  install -d "$ROOTFS_DIR/home/$LIVE_USER/.config/crixa-store/backends"
  rm -rf \
    "$ROOTFS_DIR/home/$LIVE_USER/.config/openbox" \
    "$ROOTFS_DIR/home/$LIVE_USER/.config/tint2" \
    "$ROOTFS_DIR/home/$LIVE_USER/.config/rofi" \
    "$ROOTFS_DIR/home/$LIVE_USER/.config/Thunar" \
    "$ROOTFS_DIR/home/$LIVE_USER/.config/picom" \
    "$ROOTFS_DIR/home/$LIVE_USER/.config/labwc" \
    "$ROOTFS_DIR/home/$LIVE_USER/.config/waybar" \
    "$ROOTFS_DIR/home/$LIVE_USER/.config/wofi"
  rm -f "$ROOTFS_DIR/home/$LIVE_USER/.Xresources"
  install -m 0644 "$PROJECT_ROOT/ui-shell/gtk-settings.ini" "$ROOTFS_DIR/home/$LIVE_USER/.config/gtk-3.0/settings.ini"
  install -m 0644 "$PROJECT_ROOT/plasma-shell/config/kdedefaults/package" "$ROOTFS_DIR/home/$LIVE_USER/.config/kdedefaults/package"
  install -m 0644 "$PROJECT_ROOT/plasma-shell/config/kdedefaults/kdeglobals" "$ROOTFS_DIR/home/$LIVE_USER/.config/kdedefaults/kdeglobals"
  install -m 0644 "$PROJECT_ROOT/plasma-shell/config/kdedefaults/plasmarc" "$ROOTFS_DIR/home/$LIVE_USER/.config/kdedefaults/plasmarc"
  install -m 0644 "$PROJECT_ROOT/plasma-shell/config/kdedefaults/kwinrc" "$ROOTFS_DIR/home/$LIVE_USER/.config/kdedefaults/kwinrc"
  install -m 0644 "$PROJECT_ROOT/plasma-shell/config/kdedefaults/kcminputrc" "$ROOTFS_DIR/home/$LIVE_USER/.config/kdedefaults/kcminputrc"
  install -m 0644 "$PROJECT_ROOT/plasma-shell/config/kdedefaults/ksplashrc" "$ROOTFS_DIR/home/$LIVE_USER/.config/kdedefaults/ksplashrc"
  rm -f "$ROOTFS_DIR/home/$LIVE_USER/.bash_profile" "$ROOTFS_DIR/home/$LIVE_USER/.xinitrc"
  ensure_bashrc_snippet "$ROOTFS_DIR/home/$LIVE_USER/.bashrc"

  if [[ "$(id -u)" -eq 0 ]]; then
    chroot "$ROOTFS_DIR" /bin/bash -lc "chown -R $LIVE_USER:$LIVE_USER /home/$LIVE_USER/.config"
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
    sddm
    kde-plasma-desktop
    fonts-ibm-plex
    papirus-icon-theme
    plasma-nm
    plasma-pa
    dolphin
    konsole
    systemsettings
    kde-cli-tools
    kde-config-sddm
    kio-extras
    breeze-gtk-theme
    sddm-theme-breeze
    kwin-x11
    plasma-workspace-wayland
    kwin-wayland
    qtwayland5
    xwayland
    bluedevil
    firefox-esr
    whiptail
    python3-tk
    python3-pyside2.qtwidgets
    python3-psutil
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
    wpasupplicant
    iw
    rfkill
    modemmanager
    usb-modeswitch
    bluez
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
    xdg-desktop-portal
    xdg-desktop-portal-kde
    xdg-desktop-portal-gtk
    maim
    scrot
    kde-spectacle
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
    chroot_apt_install grub-common grub2-common grub-pc-bin grub-efi-amd64-bin rsync parted gdisk dosfstools e2fsprogs whiptail
  fi
  if ! chroot "$ROOTFS_DIR" /bin/bash -lc "command -v flatpak >/dev/null 2>&1"; then
    echo "Flatpak runtime missing in rootfs; installing"
    chroot_apt_update || true
    chroot_apt_install flatpak xdg-desktop-portal xdg-desktop-portal-kde xdg-desktop-portal-gtk || true
    chroot "$ROOTFS_DIR" /bin/bash -lc "apt-get clean || true"
  fi
  if chroot "$ROOTFS_DIR" /bin/bash -lc "test -r /proc/sys/kernel/random/boot_id"; then
    chroot "$ROOTFS_DIR" /bin/bash -lc "flatpak --system remote-add --if-not-exists flathub https://dl.flathub.org/repo/flathub.flatpakrepo || true"
  else
    echo "Skipping system flatpak remote-add in sync mode (no /proc inside chroot)"
  fi
  chroot "$ROOTFS_DIR" /bin/bash -lc "apt-get clean || true"
  chroot "$ROOTFS_DIR" /bin/bash -lc "systemctl disable apt-daily.timer apt-daily-upgrade.timer man-db.timer e2scrub_all.timer fstrim.timer NetworkManager-wait-online.service lightdm.service || true"
  chroot "$ROOTFS_DIR" /bin/bash -lc "systemctl enable NetworkManager bluetooth ModemManager sddm || true"
  chroot "$ROOTFS_DIR" /bin/bash -lc "update-desktop-database /usr/share/applications || true"
  chroot "$ROOTFS_DIR" /bin/bash -lc "gtk-update-icon-cache -f /usr/share/icons/hicolor || true"
fi

echo "Synced project assets into $ROOTFS_DIR"
