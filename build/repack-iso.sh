#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
LINUX_WORK_ROOTFS="${LINUX_WORK_ROOTFS:-/var/tmp/crixa-os3-build/rootfs}"
if [[ -z "${ROOTFS_DIR:-}" ]]; then
  if [[ -d "$LINUX_WORK_ROOTFS/boot" ]]; then
    ROOTFS_DIR="$LINUX_WORK_ROOTFS"
  else
    ROOTFS_DIR="$PROJECT_ROOT/rootfs"
  fi
fi
ISO_DIR="$PROJECT_ROOT/iso"
LOG_DIR="$PROJECT_ROOT/logs"
WORK_DIR="$PROJECT_ROOT/build/work/repack"
ISO_STAGING_DIR="$WORK_DIR/iso-root"
LIVE_DIR="$ISO_STAGING_DIR/live"
ISO_PATH="$ISO_DIR/CRIXA_OS_v0.iso"
TIMESTAMP="$(date +%Y%m%d-%H%M%S)"
LOG_FILE="$LOG_DIR/repack-$TIMESTAMP.log"

mkdir -p "$LOG_DIR"
exec > >(tee -a "$LOG_FILE") 2>&1

install_host_dependencies() {
  local required_commands=(
    grub-mkimage
    grub-mkstandalone
    mksquashfs
    xorriso
    rsync
    mmd
    mkfs.vfat
  )
  local missing_commands=()
  local cmd

  for cmd in "${required_commands[@]}"; do
    if ! command -v "$cmd" >/dev/null 2>&1; then
      missing_commands+=("$cmd")
    fi
  done

  if command -v apt-get >/dev/null 2>&1 && command -v dpkg-query >/dev/null 2>&1; then
    local deps=(
      ca-certificates
      grub-common
      grub-pc-bin
      grub-efi-amd64-bin
      grub2-common
      mtools
      dosfstools
      squashfs-tools
      xorriso
      rsync
    )
    local missing=()
    local pkg
    for pkg in "${deps[@]}"; do
      if ! dpkg-query -W -f='${Status}\n' "$pkg" 2>/dev/null | grep -q "install ok installed"; then
        missing+=("$pkg")
      fi
    done
    if [[ "${#missing[@]}" -gt 0 ]]; then
      echo "Installing missing host dependencies: ${missing[*]}"
      export DEBIAN_FRONTEND=noninteractive
      apt-get update
      apt-get install -y --no-install-recommends "${missing[@]}"
    fi
    return
  fi

  if [[ "${#missing_commands[@]}" -eq 0 ]]; then
    echo "Host repack dependencies already available; skipping package-manager install step"
    return
  fi

  echo "Missing host commands: ${missing_commands[*]}"
  if command -v pacman >/dev/null 2>&1; then
    cat <<'EOF'
This host does not provide apt-get, so install the repack tools with pacman first:
  sudo pacman -S --needed grub mtools dosfstools squashfs-tools libisoburn rsync
EOF
  else
    cat <<'EOF'
This host does not provide apt-get. Install the missing commands with your system package manager,
then rerun the repack.
EOF
  fi
  exit 1
}

if [[ "$EUID" -ne 0 ]]; then
  echo "Run as root:"
  echo "  cd $PROJECT_ROOT && sudo ./build/repack-iso.sh"
  exit 1
fi

if [[ ! -d "$ROOTFS_DIR/boot" ]]; then
  echo "Rootfs missing at $ROOTFS_DIR"
  echo "Run a full build once before repack."
  exit 1
fi

echo "Using rootfs: $ROOTFS_DIR"

install_host_dependencies

SYNC_APT="${SYNC_ENABLE_APT:-0}"
if ! chroot "$ROOTFS_DIR" /bin/bash -lc "dpkg -s python3-pyside2.qtwidgets >/dev/null 2>&1"; then
  echo "Rootfs missing python3-pyside2.qtwidgets; enabling package refresh for Orbit"
  SYNC_APT=1
fi
if ! chroot "$ROOTFS_DIR" /bin/bash -lc "dpkg -s python3-psutil >/dev/null 2>&1"; then
  echo "Rootfs missing python3-psutil; enabling package refresh for Pulse"
  SYNC_APT=1
fi
if ! chroot "$ROOTFS_DIR" /bin/bash -lc "dpkg -s whiptail >/dev/null 2>&1"; then
  echo "Rootfs missing whiptail; enabling package refresh for Dockyard TTY mode"
  SYNC_APT=1
fi

mkdir -p "$ISO_DIR"
rm -rf "$WORK_DIR"
mkdir -p "$LIVE_DIR" "$ISO_STAGING_DIR/boot/grub/i386-pc" "$ISO_STAGING_DIR/EFI/boot"

echo "Refreshing rootfs content from project files"
ROOTFS_DIR="$ROOTFS_DIR" SYNC_ENABLE_APT="$SYNC_APT" "$SCRIPT_DIR/sync-rootfs.sh"

echo "Preparing live filesystem"
chroot "$ROOTFS_DIR" /bin/bash -lc "dpkg-query -W --showformat='\${Package} \${Version}\n'" > "$LIVE_DIR/filesystem.manifest"
du -sx --block-size=1 "$ROOTFS_DIR" | cut -f1 > "$LIVE_DIR/filesystem.size"

KERNEL_PATH="$(ls -1 "$ROOTFS_DIR"/boot/vmlinuz-* | sort -V | tail -n 1)"
INITRD_PATH="$(ls -1 "$ROOTFS_DIR"/boot/initrd.img-* | sort -V | tail -n 1)"
cp "$KERNEL_PATH" "$LIVE_DIR/vmlinuz"
cp "$INITRD_PATH" "$LIVE_DIR/initrd"

mksquashfs "$ROOTFS_DIR" "$LIVE_DIR/filesystem.squashfs" -wildcards -e boot

echo "Staging GRUB"
cp "$PROJECT_ROOT/boot/grub.cfg" "$ISO_STAGING_DIR/boot/grub/grub.cfg"
cp -a /usr/lib/grub/i386-pc/. "$ISO_STAGING_DIR/boot/grub/i386-pc/"

grub-mkimage \
  -O i386-pc \
  -o "$WORK_DIR/core.img" \
  -p /boot/grub \
  biosdisk iso9660 linux normal configfile search search_label

cat /usr/lib/grub/i386-pc/cdboot.img "$WORK_DIR/core.img" > "$ISO_STAGING_DIR/boot/grub/i386-pc/eltorito.img"

grub-mkstandalone \
  -O x86_64-efi \
  -o "$WORK_DIR/BOOTX64.EFI" \
  "boot/grub/grub.cfg=$PROJECT_ROOT/boot/grub.cfg"

dd if=/dev/zero of="$WORK_DIR/efiboot.img" bs=1M count=20 status=none
mkfs.vfat "$WORK_DIR/efiboot.img" >/dev/null
mmd -i "$WORK_DIR/efiboot.img" ::/EFI ::/EFI/BOOT
mcopy -i "$WORK_DIR/efiboot.img" "$WORK_DIR/BOOTX64.EFI" ::/EFI/BOOT/BOOTX64.EFI
cp "$WORK_DIR/efiboot.img" "$ISO_STAGING_DIR/EFI/boot/efiboot.img"

echo "Building ISO"
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

echo "Repack complete: $ISO_PATH"
echo "Repack log: $LOG_FILE"
