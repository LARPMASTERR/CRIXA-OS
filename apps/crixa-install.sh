#!/usr/bin/env bash
set -Eeuo pipefail

TARGET_DEV=""
TARGET_ROOT_PART=""
TARGET_EFI_PART=""
TARGET_BIOS_GRUB_PART=""
HOSTNAME_VALUE="crixa-os"
TARGET_USER="crixa"
ROOT_LABEL="CRIXA_ROOT"
TIMEZONE_VALUE="UTC"
ASSUME_YES=0
DRY_RUN=0
LOG_FILE="/var/log/crixa-installer.log"
TARGET_MOUNT="/mnt/crixa-target"
TARGET_USER_PASSWORD=""

usage() {
  cat <<'EOF'
CRIXA Installer (live -> disk)

Usage:
  crixa-install --target /dev/sdX [options]

Options:
  --target <device>       Target disk device (required), ex: /dev/sda
  --hostname <name>       Hostname to set on installed system (default: crixa-os)
  --user <name>           Primary user account (default: crixa)
  --user-password <pass>  Optional user password; if omitted, password remains empty
  --label <label>         Root filesystem label (default: CRIXA_ROOT)
  --timezone <tz>         Timezone, ex: UTC or America/New_York (default: UTC)
  --yes                   Skip destructive operation confirmation prompt
  --dry-run               Print actions without writing disk
  --log <path>            Install log path (default: /var/log/crixa-installer.log)
  -h, --help              Show this help
EOF
}

timestamp() {
  date +"%Y-%m-%d %H:%M:%S"
}

log() {
  printf '[%s] %s\n' "$(timestamp)" "$*"
}

die() {
  log "ERROR: $*"
  exit 1
}

run() {
  log "+ $*"
  if [[ "$DRY_RUN" -eq 0 ]]; then
    "$@"
  fi
}

cleanup_mounts() {
  local m
  for m in "$TARGET_MOUNT/boot/efi" "$TARGET_MOUNT/dev/pts" "$TARGET_MOUNT/dev" "$TARGET_MOUNT/proc" "$TARGET_MOUNT/sys" "$TARGET_MOUNT/run" "$TARGET_MOUNT"; do
    if mountpoint -q "$m"; then
      umount -lf "$m" || true
    fi
  done
}

trap cleanup_mounts EXIT

require_root() {
  [[ "$EUID" -eq 0 ]] || die "Run as root (use sudo)."
}

require_cmds() {
  local cmd
  for cmd in lsblk parted mkfs.ext4 mkfs.vfat blkid mount umount chroot grub-install update-grub rsync wipefs; do
    command -v "$cmd" >/dev/null 2>&1 || die "Missing command: $cmd"
  done
}

parse_args() {
  while [[ "$#" -gt 0 ]]; do
    case "$1" in
      --target)
        TARGET_DEV="${2:-}"
        shift 2
        ;;
      --hostname)
        HOSTNAME_VALUE="${2:-}"
        shift 2
        ;;
      --user)
        TARGET_USER="${2:-}"
        shift 2
        ;;
      --user-password)
        TARGET_USER_PASSWORD="${2:-}"
        shift 2
        ;;
      --label)
        ROOT_LABEL="${2:-}"
        shift 2
        ;;
      --timezone)
        TIMEZONE_VALUE="${2:-}"
        shift 2
        ;;
      --log)
        LOG_FILE="${2:-}"
        shift 2
        ;;
      --yes)
        ASSUME_YES=1
        shift
        ;;
      --dry-run)
        DRY_RUN=1
        shift
        ;;
      -h|--help)
        usage
        exit 0
        ;;
      *)
        die "Unknown argument: $1"
        ;;
    esac
  done
}

partition_name_by_index() {
  local index="$1"
  if [[ "$TARGET_DEV" =~ [0-9]$ ]]; then
    printf '%sp%s\n' "$TARGET_DEV" "$index"
  else
    printf '%s%s\n' "$TARGET_DEV" "$index"
  fi
}

confirm_destructive() {
  if [[ "$ASSUME_YES" -eq 1 ]]; then
    return
  fi
  echo
  echo "CRIXA installer will ERASE all data on: $TARGET_DEV"
  echo "Type INSTALL to continue:"
  local response
  read -r response
  [[ "$response" == "INSTALL" ]] || die "Cancelled by user."
}

validate_target() {
  [[ -n "$TARGET_DEV" ]] || die "--target is required"
  [[ -b "$TARGET_DEV" ]] || die "Target is not a block device: $TARGET_DEV"
  local dev_type
  dev_type="$(lsblk -dn -o TYPE "$TARGET_DEV" 2>/dev/null || true)"
  [[ "$dev_type" == "disk" ]] || die "Target must be a disk device (got: ${dev_type:-unknown})"
  TARGET_BIOS_GRUB_PART="$(partition_name_by_index 1)"
  TARGET_EFI_PART="$(partition_name_by_index 2)"
  TARGET_ROOT_PART="$(partition_name_by_index 3)"
}

write_target_file() {
  local rel="$1"
  local content="$2"
  local abs="$TARGET_MOUNT/$rel"
  if [[ "$DRY_RUN" -eq 1 ]]; then
    log "+ write $abs"
    return
  fi
  mkdir -p "$(dirname "$abs")"
  printf '%s\n' "$content" > "$abs"
}

sync_system() {
  local excludes=(
    --exclude=/dev/*
    --exclude=/proc/*
    --exclude=/sys/*
    --exclude=/run/*
    --exclude=/tmp/*
    --exclude=/mnt/*
    --exclude=/media/*
    --exclude=/lost+found
    --exclude=/cdrom/*
    --exclude=/swapfile
    --exclude=/var/tmp/*
    --exclude=/var/cache/apt/archives/*
  )

  log "Copying live filesystem to target disk"
  if [[ "$DRY_RUN" -eq 1 ]]; then
    log "+ rsync -aHAX --numeric-ids / $TARGET_MOUNT"
    return
  fi

  if ! rsync -aHAX --numeric-ids "${excludes[@]}" / "$TARGET_MOUNT"; then
    log "Primary rsync failed, retrying with relaxed metadata flags"
    rsync -aH --numeric-ids "${excludes[@]}" / "$TARGET_MOUNT"
  fi
}

configure_installed_system() {
  log "Configuring target system"

  local root_uuid
  local efi_uuid
  root_uuid="$(blkid -s UUID -o value "$TARGET_ROOT_PART")"
  efi_uuid="$(blkid -s UUID -o value "$TARGET_EFI_PART")"
  [[ -n "$root_uuid" ]] || die "Failed to get UUID for $TARGET_ROOT_PART"
  [[ -n "$efi_uuid" ]] || die "Failed to get UUID for $TARGET_EFI_PART"

  write_target_file "etc/fstab" "UUID=$root_uuid / ext4 defaults,noatime 0 1
UUID=$efi_uuid /boot/efi vfat umask=0077 0 1
tmpfs /tmp tmpfs defaults,nosuid,nodev 0 0"
  write_target_file "etc/hostname" "$HOSTNAME_VALUE"
  write_target_file "etc/hosts" "127.0.0.1 localhost
127.0.1.1 $HOSTNAME_VALUE"
  write_target_file "etc/lightdm/lightdm.conf.d/50-crixa-autologin.conf" "[Seat:*]
autologin-user=$TARGET_USER
autologin-user-timeout=0
user-session=openbox
greeter-hide-users=true
allow-guest=false"

  if [[ "$DRY_RUN" -eq 1 ]]; then
    log "+ chroot user/service/boot configuration"
    return
  fi

  mount --bind /dev "$TARGET_MOUNT/dev"
  mount --bind /dev/pts "$TARGET_MOUNT/dev/pts"
  mount -t proc proc "$TARGET_MOUNT/proc"
  mount -t sysfs sys "$TARGET_MOUNT/sys"
  mount --bind /run "$TARGET_MOUNT/run"

  chroot "$TARGET_MOUNT" /bin/bash -lc "id -u '$TARGET_USER' >/dev/null 2>&1 || useradd -m -s /bin/bash '$TARGET_USER'"
  chroot "$TARGET_MOUNT" /bin/bash -lc "usermod -aG sudo,audio,video,netdev,bluetooth '$TARGET_USER' || true"
  if [[ -n "$TARGET_USER_PASSWORD" ]]; then
    printf '%s:%s\n' "$TARGET_USER" "$TARGET_USER_PASSWORD" | chroot "$TARGET_MOUNT" chpasswd
  else
    chroot "$TARGET_MOUNT" /bin/bash -lc "passwd -d '$TARGET_USER' || true"
  fi

  if [[ -e "$TARGET_MOUNT/usr/share/zoneinfo/$TIMEZONE_VALUE" ]]; then
    chroot "$TARGET_MOUNT" /bin/bash -lc "ln -sf '/usr/share/zoneinfo/$TIMEZONE_VALUE' /etc/localtime && echo '$TIMEZONE_VALUE' > /etc/timezone"
  fi

  chroot "$TARGET_MOUNT" /bin/bash -lc "DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends grub-common grub2-common grub-pc-bin grub-efi-amd64-bin || true"
  chroot "$TARGET_MOUNT" /bin/bash -lc "systemctl enable NetworkManager bluetooth ModemManager lightdm || true"
  chroot "$TARGET_MOUNT" /bin/bash -lc "systemctl set-default graphical.target || true"
  chroot "$TARGET_MOUNT" /bin/bash -lc "update-initramfs -u -k all || true"
  chroot "$TARGET_MOUNT" /bin/bash -lc "grub-install --target=i386-pc '$TARGET_DEV' || true"
  chroot "$TARGET_MOUNT" /bin/bash -lc "grub-install --target=x86_64-efi --efi-directory=/boot/efi --bootloader-id=CRIXA --removable --no-nvram"
  chroot "$TARGET_MOUNT" /bin/bash -lc "update-grub"
}

main() {
  parse_args "$@"
  require_root
  require_cmds
  validate_target

  mkdir -p "$(dirname "$LOG_FILE")"
  touch "$LOG_FILE"
  chmod 0600 "$LOG_FILE" || true
  exec > >(tee -a "$LOG_FILE") 2>&1

  log "Starting CRIXA install"
  log "Target: $TARGET_DEV"
  log "Root partition: $TARGET_ROOT_PART"
  log "EFI partition: $TARGET_EFI_PART"
  log "Hostname: $HOSTNAME_VALUE"
  log "Primary user: $TARGET_USER"
  log "Timezone: $TIMEZONE_VALUE"
  [[ "$DRY_RUN" -eq 1 ]] && log "Dry-run mode enabled"

  confirm_destructive

  run wipefs -a "$TARGET_DEV"
  run parted -s "$TARGET_DEV" mklabel gpt
  run parted -s "$TARGET_DEV" mkpart primary 1MiB 3MiB
  run parted -s "$TARGET_DEV" set 1 bios_grub on
  run parted -s "$TARGET_DEV" mkpart primary fat32 3MiB 515MiB
  run parted -s "$TARGET_DEV" set 2 esp on
  run parted -s "$TARGET_DEV" mkpart primary ext4 515MiB 100%
  if [[ "$DRY_RUN" -eq 0 ]]; then
    partprobe "$TARGET_DEV" || true
    sleep 2
    [[ -b "$TARGET_EFI_PART" ]] || die "EFI partition was not created: $TARGET_EFI_PART"
    [[ -b "$TARGET_ROOT_PART" ]] || die "Root partition was not created: $TARGET_ROOT_PART"
  fi

  run mkfs.vfat -F 32 -n CRIXA_EFI "$TARGET_EFI_PART"
  run mkfs.ext4 -F -L "$ROOT_LABEL" "$TARGET_ROOT_PART"
  run mkdir -p "$TARGET_MOUNT"
  run mount "$TARGET_ROOT_PART" "$TARGET_MOUNT"
  run mkdir -p "$TARGET_MOUNT/boot/efi"
  run mount "$TARGET_EFI_PART" "$TARGET_MOUNT/boot/efi"

  sync_system
  configure_installed_system

  run sync
  log "Install complete. You can reboot and boot from $TARGET_DEV."
  log "Installer log: $LOG_FILE"
}

main "$@"
