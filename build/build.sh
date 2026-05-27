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
    echo "  cd $PROJECT_ROOT && sudo ./build/build.sh"
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
  local required_commands=(
    debootstrap
    grub-mkimage
    grub-mkstandalone
    mksquashfs
    xorriso
    rsync
    mmd
    mkfs.vfat
    openssl
  )
  local missing_commands=()
  local cmd

  for cmd in "${required_commands[@]}"; do
    if ! command -v "$cmd" >/dev/null 2>&1; then
      missing_commands+=("$cmd")
    fi
  done

  if command -v apt-get >/dev/null 2>&1 && command -v dpkg-query >/dev/null 2>&1; then
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
    return
  fi

  if [[ "${#missing_commands[@]}" -eq 0 ]]; then
    log "Host build dependencies already available; skipping package-manager install step"
    return
  fi

  echo "Missing host commands: ${missing_commands[*]}"
  if command -v pacman >/dev/null 2>&1; then
    cat <<'EOF'
This host does not provide apt-get, so install the build tools with pacman first:
  sudo pacman -S --needed debootstrap grub mtools dosfstools squashfs-tools libisoburn rsync openssl

Optional but helpful for Debian package inspection on Arch:
  sudo pacman -S --needed dpkg
EOF
  else
    cat <<'EOF'
This host does not provide apt-get. Install the missing commands with your system package manager,
then rerun the build.
EOF
  fi
  exit 1
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
  dbus-user-session \
  xorg \
  sddm \
  kde-plasma-desktop \
  plasma-nm \
  plasma-pa \
  dolphin \
  konsole \
  systemsettings \
  kde-cli-tools \
  kde-config-sddm \
  kio-extras \
  breeze-gtk-theme \
  sddm-theme-breeze \
  kwin-x11 \
  plasma-workspace-wayland \
  kwin-wayland \
  qtwayland5 \
  bluedevil \
  alacritty \
  xterm \
  firefox-esr \
  ffmpeg \
  libavcodec-extra \
  gvfs \
  gvfs-backends \
  flatpak \
  xdg-desktop-portal \
  xdg-desktop-portal-kde \
  xdg-desktop-portal-gtk \
  network-manager \
  wpasupplicant \
  iw \
  rfkill \
  modemmanager \
  usb-modeswitch \
  bluez \
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
  sudo \
  feh \
  maim \
  scrot \
  kde-spectacle \
  xclip \
  wl-clipboard \
  grim \
  slurp \
  libnotify-bin \
  xdg-utils \
  x11-xserver-utils \
  fonts-ibm-plex \
  fonts-dejavu-core \
  papirus-icon-theme \
  desktop-file-utils \
  neofetch \
  whiptail \
  python3-tk \
  python3-pyside2.qtwidgets \
  python3-psutil \
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

systemctl disable lightdm || true
systemctl enable NetworkManager || true
systemctl enable bluetooth || true
systemctl enable ModemManager || true
systemctl enable sddm || true
systemctl set-default graphical.target
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
  rm -f "$ROOTFS_DIR/etc/skel/.bash_profile" "$ROOTFS_DIR/etc/skel/.xinitrc"
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
  chroot "$ROOTFS_DIR" /bin/bash -lc "cp -a /etc/skel/. /home/$LIVE_USER/ && chown -R $LIVE_USER:$LIVE_USER /home/$LIVE_USER"
  rm -f "$ROOTFS_DIR/home/$LIVE_USER/.bash_profile" "$ROOTFS_DIR/home/$LIVE_USER/.xinitrc"
  ensure_bashrc_snippet "$ROOTFS_DIR/home/$LIVE_USER/.bashrc"
  chroot "$ROOTFS_DIR" /bin/bash -lc "systemctl disable apt-daily.timer apt-daily-upgrade.timer man-db.timer e2scrub_all.timer fstrim.timer NetworkManager-wait-online.service lightdm.service || true"
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
  require_file "$PROJECT_ROOT/themes/CRIXA/index.theme"
  require_file "$PROJECT_ROOT/ui-shell/gtk-settings.ini"
  require_file "$PROJECT_ROOT/ui-shell/xorg-input.conf"
  require_file "$PROJECT_ROOT/ui-shell/bashrc-crixa-snippet"
  require_file "$PROJECT_ROOT/apps/crixa-settings.sh"
  require_file "$PROJECT_ROOT/apps/crixa-settings.py"
  require_file "$PROJECT_ROOT/apps/crixa-store.sh"
  require_file "$PROJECT_ROOT/apps/crixa-store.py"
  require_file "$PROJECT_ROOT/apps/crixa-install.sh"
  require_file "$PROJECT_ROOT/apps/crixa-installer.sh"
  require_file "$PROJECT_ROOT/apps/crixa-installer.py"
  require_file "$PROJECT_ROOT/apps/crixa-installer-helper.py"
  require_file "$PROJECT_ROOT/apps/org.crixa.dockyard.policy"
  require_file "$PROJECT_ROOT/apps/crixa-updater.sh"
  require_file "$PROJECT_ROOT/apps/crixa-updater.py"
  require_file "$PROJECT_ROOT/apps/crixa-updater-helper.py"
  require_file "$PROJECT_ROOT/apps/org.crixa.transit.policy"
  require_file "$PROJECT_ROOT/apps/crixa-session-mode.sh"
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
  require_file "$PROJECT_ROOT/apps/crixa-task-manager-helper.py"
  require_file "$PROJECT_ROOT/apps/org.crixa.pulse.policy"
  require_file "$PROJECT_ROOT/apps/crixa-fetch.sh"
  require_file "$PROJECT_ROOT/apps/crixa-shell-bootstrap.sh"
  require_file "$PROJECT_ROOT/apps/fastfetch.sh"
  require_file "$PROJECT_ROOT/apps/neofetch.sh"
  require_file "$PROJECT_ROOT/apps/crixa-settings.desktop"
  require_file "$PROJECT_ROOT/apps/crixa-welcome.sh"
  require_file "$PROJECT_ROOT/apps/crixa-welcome.py"
  require_file "$PROJECT_ROOT/apps/crixa-welcome.desktop"
  require_file "$PROJECT_ROOT/apps/crixa-browser.desktop"
  require_file "$PROJECT_ROOT/apps/crixa-dashboard.py"
  require_file "$PROJECT_ROOT/apps/crixa-launcher.desktop"
  require_file "$PROJECT_ROOT/apps/crixa-terminal.desktop"
  require_file "$PROJECT_ROOT/apps/crixa-files.desktop"
  require_file "$PROJECT_ROOT/apps/crixa-youtube.desktop"
  require_file "$PROJECT_ROOT/apps/crixa-wallpapers.desktop"
  require_file "$PROJECT_ROOT/apps/crixa-task-manager.desktop"
  require_file "$PROJECT_ROOT/apps/crixa-store.desktop"
  require_file "$PROJECT_ROOT/apps/crixa-installer.desktop"
  require_file "$PROJECT_ROOT/apps/crixa-updater.desktop"
  require_file "$PROJECT_ROOT/apps/crixa-wayland-control.desktop"
  require_file "$PROJECT_ROOT/Wallpapers/DefaultWP.jpeg"
  require_file "$PROJECT_ROOT/assets/wallpapers/crixa-wallpaper.svg"
  require_file "$PROJECT_ROOT/assets/wallpapers/crixa-wallpaper-mist-mountains.jpg"
  require_file "$PROJECT_ROOT/assets/wallpapers/crixa-wallpaper-sand-ridges.jpg"
  require_file "$PROJECT_ROOT/assets/wallpapers/crixa-wallpaper-cloud-coast.jpg"
  require_file "$PROJECT_ROOT/assets/wallpapers/crixa-wallpaper-fog-ocean.jpg"
  require_file "$PROJECT_ROOT/assets/wallpapers/crixa-wallpaper-snow-quiet.jpg"
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
  require_file "$PROJECT_ROOT/store-packages/catalog.json"
  require_file "$PROJECT_ROOT/store-packages/assets/README.md"
  require_file "$PROJECT_ROOT/store-packages/system-rollouts.json"
  require_file "$PROJECT_ROOT/store-packages/packages/lumen-notes/payload/bin/lumen-notes"
  require_file "$PROJECT_ROOT/store-backends/backend-crixa-repo.py"
  require_file "$PROJECT_ROOT/store-backends/backend-flatpak.py"
  require_file "$PROJECT_ROOT/store-backends/crixa-store-system-helper.py"
  require_file "$PROJECT_ROOT/store-backends/org.crixa.store.policy"
  require_file "$PROJECT_ROOT/store-backends/manifests/crixa-repo.json"
  require_file "$PROJECT_ROOT/store-backends/manifests/flathub.json"
  require_file "$PROJECT_ROOT/store-backends/extensions/README.md"
  require_file "$PROJECT_ROOT/store-backends/extensions/example-template.py"
  require_file "$PROJECT_ROOT/build/build-crixa-repo.sh"

  for package_dir in "$PROJECT_ROOT"/store-packages/packages/*; do
    [[ -d "$package_dir" ]] || continue
    package_id="$(basename "$package_dir")"
    require_file "$package_dir/payload/bin/$package_id"
    require_file "$package_dir/payload/applications/$package_id.desktop"
    require_file "$package_dir/payload/icons/hicolor/scalable/apps/$package_id.svg"
  done

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
