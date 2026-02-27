#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

LINUX_WORK_BASE="${LINUX_WORK_BASE:-/var/tmp/crixa-os3-build}"
BUILD_WORK_DIR="$LINUX_WORK_BASE/work"
ROOTFS_DIR="$LINUX_WORK_BASE/rootfs"
PROJECT_ROOTFS_DIR="$PROJECT_ROOT/rootfs"
ISO_DIR="$PROJECT_ROOT/iso"
LOG_DIR="$PROJECT_ROOT/logs"
ISO_STAGING_DIR="$BUILD_WORK_DIR/iso-root"
LIVE_DIR="$ISO_STAGING_DIR/live"

DIST="${DIST:-bookworm}"
ARCH="${ARCH:-amd64}"
MIRROR="${MIRROR:-https://deb.debian.org/debian}"
LIVE_USER="${LIVE_USER:-crixa}"
HOSTNAME_VALUE="${HOSTNAME_VALUE:-crixa-os}"
CRIXA_VERSION="${CRIXA_VERSION:-0.0.0}"
CRIXA_TRACK="${CRIXA_TRACK:-stable}"
ISO_NAME="CRIXA_OS_v0.iso"
ISO_PATH="$ISO_DIR/$ISO_NAME"
TIMESTAMP="$(date +%Y%m%d-%H%M%S)"
CRIXA_BUILD_ID="${CRIXA_BUILD_ID:-$TIMESTAMP}"
BUILD_LOG="$LOG_DIR/build-$TIMESTAMP.log"
PACKAGE_LOG="$LOG_DIR/package-install-$TIMESTAMP.log"

mkdir -p "$LOG_DIR"
exec > >(tee -a "$BUILD_LOG") 2>&1

log() {
  printf '[%s] %s\n' "$(date +%H:%M:%S)" "$*"
}

fail_log() {
  local line="$1"
  local code="$2"
  {
    echo "[$(date -Is)] build failed at line $line (exit code $code)"
    echo "build log: $BUILD_LOG"
    echo "package log: $PACKAGE_LOG"
  } >> "$LOG_DIR/build-failures.log"
}

cleanup_mounts() {
  local mount_path
  for mount_path in "$ROOTFS_DIR/dev/pts" "$ROOTFS_DIR/dev" "$ROOTFS_DIR/proc" "$ROOTFS_DIR/sys"; do
    if mountpoint -q "$mount_path"; then
      umount -lf "$mount_path"
    fi
  done
}

trap 'fail_log "$LINENO" "$?"' ERR
trap cleanup_mounts EXIT

require_root() {
  if [[ "$EUID" -ne 0 ]]; then
    echo "This script must run as root. Example:"
    echo "  wsl -u root bash -lc 'cd /mnt/c/Users/[USER]/Desktop/OS3 && ./build/build.sh'"
    exit 1
  fi
}

require_file() {
  local f="$1"
  if [[ ! -f "$f" ]]; then
    echo "Missing required file: $f"
    exit 1
  fi
}

install_host_dependencies() {
  log "Installing host build dependencies"
  export DEBIAN_FRONTEND=noninteractive
  apt-get update
  apt-get install -y --no-install-recommends \
    ca-certificates \
    debian-archive-keyring \
    debootstrap \
    openssl \
    grub-common \
    grub-pc-bin \
    grub-efi-amd64-bin \
    grub2-common \
    mtools \
    dosfstools \
    rsync \
    squashfs-tools \
    xorriso
}

reset_workspace() {
  log "Resetting build workspace"
  rm -rf "$BUILD_WORK_DIR" "$ROOTFS_DIR" "$PROJECT_ROOTFS_DIR"
  mkdir -p "$BUILD_WORK_DIR" "$ROOTFS_DIR" "$PROJECT_ROOTFS_DIR" "$ISO_DIR" "$LIVE_DIR"
  rm -f "$ISO_PATH"
  log "Linux work dir: $LINUX_WORK_BASE"
  log "Project rootfs export dir: $PROJECT_ROOTFS_DIR"
}

bootstrap_rootfs() {
  log "Bootstrapping Debian $DIST root filesystem"
  debootstrap --arch="$ARCH" --variant=minbase "$DIST" "$ROOTFS_DIR" "$MIRROR"
}

mount_chroot_filesystems() {
  log "Mounting chroot filesystems"
  mkdir -p "$ROOTFS_DIR/dev/pts" "$ROOTFS_DIR/proc" "$ROOTFS_DIR/sys"
  mount --bind /dev "$ROOTFS_DIR/dev"
  mount --bind /dev/pts "$ROOTFS_DIR/dev/pts"
  mount -t proc proc "$ROOTFS_DIR/proc"
  mount -t sysfs sys "$ROOTFS_DIR/sys"
  cp -L /etc/resolv.conf "$ROOTFS_DIR/etc/resolv.conf"
}

write_chroot_setup_script() {
  cat > "$BUILD_WORK_DIR/chroot-setup.sh" <<EOF
#!/usr/bin/env bash
set -Eeuo pipefail

LIVE_USER="$LIVE_USER"
HOSTNAME_VALUE="$HOSTNAME_VALUE"
export DEBIAN_FRONTEND=noninteractive

cat > /etc/apt/sources.list <<APTEOF
deb $MIRROR $DIST main contrib non-free non-free-firmware
deb https://security.debian.org/debian-security $DIST-security main contrib non-free non-free-firmware
deb $MIRROR $DIST-updates main contrib non-free non-free-firmware
APTEOF

apt-get update
apt-get install -y --no-install-recommends \
  linux-image-amd64 \
  linux-headers-amd64 \
  dkms \
  live-boot \
  systemd-sysv \
  locales \
  ca-certificates \
  dbus-x11 \
  xorg \
  xinit \
  lightdm \
  lightdm-gtk-greeter \
  openbox \
  tint2 \
  rofi \
  alacritty \
  xterm \
  picom \
  firefox-esr \
  ffmpeg \
  libavcodec-extra \
  thunar \
  thunar-volman \
  gvfs \
  gvfs-backends \
  flatpak \
  xdg-desktop-portal \
  xdg-desktop-portal-gtk \
  network-manager \
  network-manager-gnome \
  wpasupplicant \
  iw \
  rfkill \
  modemmanager \
  usb-modeswitch \
  bluez \
  blueman \
  pipewire \
  pipewire-pulse \
  wireplumber \
  libspa-0.2-bluetooth \
  alsa-utils \
  pulseaudio-utils \
  pavucontrol \
  mesa-utils \
  libgl1-mesa-dri \
  mesa-vulkan-drivers \
  xserver-xorg-video-all \
  xserver-xorg-input-all \
  pciutils \
  usbutils \
  dmidecode \
  parted \
  rsync \
  firmware-linux \
  firmware-linux-nonfree \
  firmware-amd-graphics \
  nvidia-driver \
  nvidia-vulkan-icd \
  nvidia-smi \
  nvidia-settings \
  firmware-nvidia-gsp \
  grub-common \
  grub2-common \
  grub-pc-bin \
  grub-efi-amd64-bin \
  gdisk \
  dosfstools \
  e2fsprogs \
  xwayland \
  weston \
  sudo \
  feh \
  maim \
  scrot \
  xclip \
  wl-clipboard \
  grim \
  slurp \
  libnotify-bin \
  xdg-utils \
  x11-xserver-utils \
  fonts-dejavu-core \
  desktop-file-utils \
  neofetch \
  python3-tk \
  plymouth \
  plymouth-themes

for pkg in \
  firmware-linux-free \
  firmware-realtek \
  firmware-iwlwifi \
  firmware-atheros \
  firmware-brcm80211 \
  firmware-misc-nonfree \
  intel-microcode \
  amd64-microcode \
  vulkan-tools \
  mesa-va-drivers \
  mesa-vdpau-drivers \
  intel-media-va-driver-non-free \
  va-driver-all \
  nvidia-detect \
; do
  apt-get install -y --no-install-recommends "\$pkg" || true
done

DEBIAN_FRONTEND=noninteractive dpkg --configure -a || true
DEBIAN_FRONTEND=noninteractive apt-get -f install -y || true

apt-get clean

flatpak --system remote-add --if-not-exists flathub https://dl.flathub.org/repo/flathub.flatpakrepo || true

update-alternatives --set x-www-browser /usr/bin/firefox-esr || true
update-alternatives --set gnome-www-browser /usr/bin/firefox-esr || true
plymouth-set-default-theme spinner || true

echo "en_US.UTF-8 UTF-8" > /etc/locale.gen
locale-gen
update-locale LANG=en_US.UTF-8

if ! id -u "\$LIVE_USER" >/dev/null 2>&1; then
  useradd -m -s /bin/bash "\$LIVE_USER"
fi
usermod -aG sudo,audio,video,netdev,bluetooth "\$LIVE_USER"
passwd -d "\$LIVE_USER" || true

cat > /etc/sudoers.d/90-\$LIVE_USER <<SUDOEOF
\$LIVE_USER ALL=(ALL) NOPASSWD:ALL
SUDOEOF
chmod 0440 /etc/sudoers.d/90-\$LIVE_USER

cat > /etc/hostname <<HOSTEOF
\$HOSTNAME_VALUE
HOSTEOF

cat > /etc/hosts <<HOSTSEOF
127.0.0.1 localhost
127.0.1.1 \$HOSTNAME_VALUE
HOSTSEOF

mkdir -p /etc/lightdm/lightdm.conf.d
cat > /etc/lightdm/lightdm.conf.d/50-crixa-autologin.conf <<LIGHTDMEOF
[Seat:*]
autologin-user=\$LIVE_USER
autologin-user-timeout=0
user-session=openbox
greeter-hide-users=true
allow-guest=false
LIGHTDMEOF

systemctl enable NetworkManager || true
systemctl enable bluetooth || true
systemctl enable ModemManager || true
systemctl enable lightdm || true
systemctl set-default graphical.target

mkdir -p /etc/skel/.config/openbox /etc/skel/.config/tint2 /etc/skel/.config/rofi /etc/skel/.config/gtk-3.0

cat > /etc/skel/.bash_profile <<PROFILEEOF
if [ -z "\${DISPLAY:-}" ] && [ "\$(tty)" = "/dev/tty1" ]; then
  exec startx
fi
PROFILEEOF

cat > /etc/skel/.xinitrc <<XINITEOF
#!/bin/sh
export XDG_CURRENT_DESKTOP=CRIXA
export XDG_SESSION_DESKTOP=crixa
export GTK_THEME=CRIXA
if [ -f "\$HOME/.Xresources" ]; then
  xrdb -merge "\$HOME/.Xresources"
fi
exec openbox-session
XINITEOF
chmod +x /etc/skel/.xinitrc
EOF

  chmod +x "$BUILD_WORK_DIR/chroot-setup.sh"
}

run_chroot_setup() {
  log "Installing desktop stack inside rootfs"
  install -m 0755 "$BUILD_WORK_DIR/chroot-setup.sh" "$ROOTFS_DIR/tmp/chroot-setup.sh"
  chroot "$ROOTFS_DIR" /bin/bash -lc "/tmp/chroot-setup.sh" 2>&1 | tee "$PACKAGE_LOG"
  rm -f "$ROOTFS_DIR/tmp/chroot-setup.sh"
}

install_crixa_assets() {
  log "Installing CRIXA theme and shell assets"
  chmod +x "$PROJECT_ROOT/build/build-crixa-repo.sh"
  "$PROJECT_ROOT/build/build-crixa-repo.sh"
  require_file "$PROJECT_ROOT/crixa-repo/metadata/repo.json"
  require_file "$PROJECT_ROOT/crixa-repo/metadata/repo.sig"
  require_file "$PROJECT_ROOT/crixa-repo/metadata/system-updates.json"
  require_file "$PROJECT_ROOT/crixa-repo/metadata/system-updates.sig"
  require_file "$PROJECT_ROOT/crixa-repo/keys/repo-public.pem"

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
  chroot "$ROOTFS_DIR" /bin/bash -lc "cp -a /etc/skel/. /home/$LIVE_USER/ && chown -R $LIVE_USER:$LIVE_USER /home/$LIVE_USER"
  ensure_bashrc_snippet "$ROOTFS_DIR/home/$LIVE_USER/.bashrc"
  chroot "$ROOTFS_DIR" /bin/bash -lc "systemctl disable apt-daily.timer apt-daily-upgrade.timer man-db.timer e2scrub_all.timer fstrim.timer NetworkManager-wait-online.service || true"
  chroot "$ROOTFS_DIR" /bin/bash -lc "gtk-update-icon-cache -f /usr/share/icons/hicolor || true"
  chroot "$ROOTFS_DIR" /bin/bash -lc "update-desktop-database /usr/share/applications || true"
  chroot "$ROOTFS_DIR" /bin/bash -lc "update-initramfs -u -k all"
}

create_live_filesystem() {
  log "Creating SquashFS and live boot artifacts"

  chroot "$ROOTFS_DIR" /bin/bash -lc "dpkg-query -W --showformat='\${Package} \${Version}\n'" > "$LIVE_DIR/filesystem.manifest"
  du -sx --block-size=1 "$ROOTFS_DIR" | cut -f1 > "$LIVE_DIR/filesystem.size"

  local kernel_path
  local initrd_path
  kernel_path="$(ls -1 "$ROOTFS_DIR"/boot/vmlinuz-* | sort -V | tail -n 1)"
  initrd_path="$(ls -1 "$ROOTFS_DIR"/boot/initrd.img-* | sort -V | tail -n 1)"
  cp "$kernel_path" "$LIVE_DIR/vmlinuz"
  cp "$initrd_path" "$LIVE_DIR/initrd"

  cleanup_mounts
  mksquashfs "$ROOTFS_DIR" "$LIVE_DIR/filesystem.squashfs" -wildcards -e boot
}

sync_rootfs_to_project() {
  log "Exporting rootfs snapshot into project/rootfs"
  if ! rsync -a --delete \
      --exclude='dev/*' \
      --exclude='proc/*' \
      --exclude='sys/*' \
      --exclude='run/*' \
      --exclude='tmp/*' \
      "$ROOTFS_DIR"/ "$PROJECT_ROOTFS_DIR"/; then
    log "Primary rootfs export failed, retrying with relaxed metadata flags"
    rsync -rlt --delete \
      --no-perms \
      --no-owner \
      --no-group \
      --exclude='dev/*' \
      --exclude='proc/*' \
      --exclude='sys/*' \
      --exclude='run/*' \
      --exclude='tmp/*' \
      "$ROOTFS_DIR"/ "$PROJECT_ROOTFS_DIR"/
  fi
}

stage_grub_payload() {
  log "Staging GRUB configuration"
  install -d "$ISO_STAGING_DIR/boot/grub"
  cp "$PROJECT_ROOT/boot/grub.cfg" "$ISO_STAGING_DIR/boot/grub/grub.cfg"

  install -d "$ISO_STAGING_DIR/boot/grub/i386-pc"
  cp -a /usr/lib/grub/i386-pc/. "$ISO_STAGING_DIR/boot/grub/i386-pc/"

  grub-mkimage \
    -O i386-pc \
    -o "$BUILD_WORK_DIR/core.img" \
    -p /boot/grub \
    biosdisk iso9660 linux normal configfile search search_label

  cat /usr/lib/grub/i386-pc/cdboot.img "$BUILD_WORK_DIR/core.img" > "$ISO_STAGING_DIR/boot/grub/i386-pc/eltorito.img"

  install -d "$ISO_STAGING_DIR/EFI/boot"
  grub-mkstandalone \
    -O x86_64-efi \
    -o "$BUILD_WORK_DIR/BOOTX64.EFI" \
    "boot/grub/grub.cfg=$PROJECT_ROOT/boot/grub.cfg"

  dd if=/dev/zero of="$BUILD_WORK_DIR/efiboot.img" bs=1M count=20 status=none
  mkfs.vfat "$BUILD_WORK_DIR/efiboot.img" >/dev/null
  mmd -i "$BUILD_WORK_DIR/efiboot.img" ::/EFI ::/EFI/BOOT
  mcopy -i "$BUILD_WORK_DIR/efiboot.img" "$BUILD_WORK_DIR/BOOTX64.EFI" ::/EFI/BOOT/BOOTX64.EFI
  cp "$BUILD_WORK_DIR/efiboot.img" "$ISO_STAGING_DIR/EFI/boot/efiboot.img"
}

build_iso() {
  log "Building ISO with xorriso"
  xorriso -as mkisofs \
    -iso-level 3 \
    -full-iso9660-filenames \
    -volid "CRIXA_OS_V0" \
    -eltorito-boot boot/grub/i386-pc/eltorito.img \
      -no-emul-boot \
      -boot-load-size 4 \
      -boot-info-table \
      --grub2-boot-info \
      --grub2-mbr /usr/lib/grub/i386-pc/boot_hybrid.img \
    -eltorito-alt-boot \
    -e EFI/boot/efiboot.img \
      -no-emul-boot \
    -isohybrid-gpt-basdat \
    -output "$ISO_PATH" \
    "$ISO_STAGING_DIR"
}

main() {
  require_root

  require_file "$PROJECT_ROOT/boot/grub.cfg"
  require_file "$PROJECT_ROOT/themes/CRIXA/gtk.css"
  require_file "$PROJECT_ROOT/themes/CRIXA/openbox-themerc"
  require_file "$PROJECT_ROOT/ui-shell/rc.xml"
  require_file "$PROJECT_ROOT/ui-shell/menu.xml"
  require_file "$PROJECT_ROOT/ui-shell/autostart"
  require_file "$PROJECT_ROOT/ui-shell/tint2rc"
  require_file "$PROJECT_ROOT/ui-shell/rofi.rasi"
  require_file "$PROJECT_ROOT/ui-shell/picom.conf"
  require_file "$PROJECT_ROOT/ui-shell/thunar-uca.xml"
  require_file "$PROJECT_ROOT/ui-shell/thunarrc"
  require_file "$PROJECT_ROOT/ui-shell/xorg-input.conf"
  require_file "$PROJECT_ROOT/apps/crixa-settings.sh"
  require_file "$PROJECT_ROOT/apps/crixa-settings.py"
  require_file "$PROJECT_ROOT/apps/crixa-store.sh"
  require_file "$PROJECT_ROOT/apps/crixa-store.py"
  require_file "$PROJECT_ROOT/apps/crixa-install.sh"
  require_file "$PROJECT_ROOT/apps/crixa-installer.sh"
  require_file "$PROJECT_ROOT/apps/crixa-installer.py"
  require_file "$PROJECT_ROOT/apps/crixa-updater.sh"
  require_file "$PROJECT_ROOT/apps/crixa-updater.py"
  require_file "$PROJECT_ROOT/apps/crixa-session-mode.sh"
  require_file "$PROJECT_ROOT/apps/crixa-wayland-session.sh"
  require_file "$PROJECT_ROOT/apps/crixa-wayland-control.sh"
  require_file "$PROJECT_ROOT/apps/crixa-wayland-control.py"
  require_file "$PROJECT_ROOT/apps/crixa-releasectl.sh"
  require_file "$PROJECT_ROOT/apps/crixa-releasectl.py"
  require_file "$PROJECT_ROOT/apps/crixapkg.sh"
  require_file "$PROJECT_ROOT/apps/crixapkg.py"
  require_file "$PROJECT_ROOT/apps/crixa-browser.sh"
  require_file "$PROJECT_ROOT/apps/crixa-terminal.sh"
  require_file "$PROJECT_ROOT/apps/crixa-files.sh"
  require_file "$PROJECT_ROOT/apps/crixa-menu.sh"
  require_file "$PROJECT_ROOT/apps/crixa-wallpaper.sh"
  require_file "$PROJECT_ROOT/apps/crixa-screenshot.sh"
  require_file "$PROJECT_ROOT/apps/crixa-task-manager.sh"
  require_file "$PROJECT_ROOT/apps/crixa-task-manager.py"
  require_file "$PROJECT_ROOT/apps/crixa-fetch.sh"
  require_file "$PROJECT_ROOT/apps/neofetch.sh"
  require_file "$PROJECT_ROOT/apps/crixa-settings.desktop"
  require_file "$PROJECT_ROOT/apps/crixa-browser.desktop"
  require_file "$PROJECT_ROOT/apps/crixa-launcher.desktop"
  require_file "$PROJECT_ROOT/apps/crixa-terminal.desktop"
  require_file "$PROJECT_ROOT/apps/crixa-files.desktop"
  require_file "$PROJECT_ROOT/apps/crixa-youtube.desktop"
  require_file "$PROJECT_ROOT/apps/crixa-wallpapers.desktop"
  require_file "$PROJECT_ROOT/apps/crixa-task-manager.desktop"
  require_file "$PROJECT_ROOT/apps/crixa-store.desktop"
  require_file "$PROJECT_ROOT/apps/crixa-installer.desktop"
  require_file "$PROJECT_ROOT/apps/crixa-updater.desktop"
  require_file "$PROJECT_ROOT/apps/crixa-wayland-session.desktop"
  require_file "$PROJECT_ROOT/apps/crixa-wayland-control.desktop"
  require_file "$PROJECT_ROOT/assets/wallpapers/crixa-wallpaper.jpg"
  require_file "$PROJECT_ROOT/assets/wallpapers/crixa-wallpaper.svg"
  require_file "$PROJECT_ROOT/assets/wallpapers/crixa-wallpaper-orbit.jpg"
  require_file "$PROJECT_ROOT/assets/wallpapers/crixa-wallpaper-nebula.jpg"
  require_file "$PROJECT_ROOT/assets/wallpapers/crixa-wallpaper-planet.jpg"
  require_file "$PROJECT_ROOT/assets/wallpapers/crixa-wallpaper-saturn.jpg"
  require_file "$PROJECT_ROOT/assets/wallpapers/crixa-wallpaper-jupiter.jpg"
  require_file "$PROJECT_ROOT/assets/wallpapers/crixa-wallpaper-aurora.jpg"
  require_file "$PROJECT_ROOT/assets/wallpapers/crixa-wallpaper-rings.jpg"
  require_file "$PROJECT_ROOT/assets/wallpapers/crixa-wallpaper-uranus.jpg"
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
  require_file "$PROJECT_ROOT/ui-shell/bashrc-crixa-snippet"
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

  install_host_dependencies
  reset_workspace
  bootstrap_rootfs
  mount_chroot_filesystems
  write_chroot_setup_script
  run_chroot_setup
  install_crixa_assets
  create_live_filesystem
  sync_rootfs_to_project
  stage_grub_payload
  build_iso

  log "Build complete: $ISO_PATH"
  log "Build log: $BUILD_LOG"
  log "Package log: $PACKAGE_LOG"
}

main "$@"
