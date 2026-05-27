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
JSON_OUTPUT=0
PROBE_ONLY=0
VALIDATE_ONLY=0
LOG_FILE="/var/log/crixa-installer.log"
TARGET_MOUNT="/mnt/crixa-target"
TARGET_USER_PASSWORD=""

usage() {
  cat <<'EOF'
Dockyard (live -> disk)

Usage:
  crixa-install --target /dev/sdX [options]
  crixa-install --probe --json

Options:
  --target <device>       Target disk device (required), ex: /dev/sda
  --hostname <name>       Hostname to set on installed system (default: crixa-os)
  --user <name>           Primary user account (default: crixa)
  --user-password <pass>  Optional user password; if omitted, password remains empty
  --label <label>         Root filesystem label (default: CRIXA_ROOT)
  --timezone <tz>         Timezone, ex: UTC or America/New_York (default: UTC)
  --yes                   Skip destructive operation confirmation prompt
  --dry-run               Print the install plan without writing disk
  --json                  Emit line-delimited JSON events for frontends
  --probe                 List candidate disks and exit
  --validate-target       Validate the selected target and exit
  --log <path>            Install log path (default: /var/log/crixa-installer.log)
  -h, --help              Show this help
EOF
}

timestamp() {
  date +"%Y-%m-%d %H:%M:%S"
}

json_emit() {
  local event="$1"
  local message="${2:-}"
  local progress="${3:-}"
  local stage="${4:-}"
  python3 - "$event" "$message" "$progress" "$stage" <<'PY'
import datetime
import json
import sys

event, message, progress, stage = sys.argv[1:5]
payload = {
    "event": event,
    "message": message,
    "time": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
}
if progress:
    try:
        payload["progress"] = int(progress)
    except ValueError:
        pass
if stage:
    payload["stage"] = stage
print(json.dumps(payload, ensure_ascii=True), flush=True)
PY
}

append_log_file() {
  local line="$1"
  if [[ -z "$LOG_FILE" ]]; then
    return
  fi
  mkdir -p "$(dirname "$LOG_FILE")" 2>/dev/null || return
  printf '%s\n' "$line" >> "$LOG_FILE" 2>/dev/null || true
}

log() {
  local line="[$(timestamp)] $*"
  if [[ "$JSON_OUTPUT" -eq 1 ]]; then
    append_log_file "$line"
    json_emit "log" "$*"
  else
    printf '%s\n' "$line"
  fi
}

stage() {
  local name="$1"
  local progress="$2"
  local message="$3"
  if [[ "$JSON_OUTPUT" -eq 1 ]]; then
    append_log_file "[$(timestamp)] [$name] $message"
    json_emit "stage" "$message" "$progress" "$name"
  else
    log "$message"
  fi
}

die() {
  if [[ "$JSON_OUTPUT" -eq 1 ]]; then
    append_log_file "[$(timestamp)] ERROR: $*"
    json_emit "error" "$*"
  else
    log "ERROR: $*"
  fi
  exit 1
}

run() {
  log "+ $*"
  if [[ "$DRY_RUN" -eq 1 ]]; then
    return
  fi
  if [[ "$JSON_OUTPUT" -eq 1 ]]; then
    if ! "$@" >> "$LOG_FILE" 2>&1; then
      die "Command failed: $*"
    fi
  else
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

on_error() {
  local line="${1:-unknown}"
  if [[ "$JSON_OUTPUT" -eq 1 ]]; then
    append_log_file "[$(timestamp)] ERROR: Install failed near line $line"
    json_emit "error" "Install failed near line $line. See $LOG_FILE"
  else
    log "ERROR: Install failed near line $line"
  fi
}

trap 'on_error "$LINENO"' ERR
trap cleanup_mounts EXIT

require_root() {
  [[ "$EUID" -eq 0 ]] || die "Run as root (use pkexec or sudo)."
}

require_cmds() {
  local cmd
  local required=(lsblk findmnt)
  if [[ "$DRY_RUN" -eq 0 && "$VALIDATE_ONLY" -eq 0 ]]; then
    required=(lsblk parted mkfs.ext4 mkfs.vfat blkid mount umount chroot grub-install update-grub rsync wipefs findmnt)
  fi
  for cmd in "${required[@]}"; do
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
      --json)
        JSON_OUTPUT=1
        shift
        ;;
      --probe)
        PROBE_ONLY=1
        shift
        ;;
      --validate-target)
        VALIDATE_ONLY=1
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

probe_disks() {
  local lsblk_json
  lsblk_json="$(lsblk -J -o PATH,NAME,SIZE,MODEL,TYPE,RM,ROTA,TRAN,VENDOR,SERIAL,MOUNTPOINTS 2>/dev/null || true)"
  python3 - "$lsblk_json" <<'PY'
import json
import sys

try:
    payload = json.loads(sys.argv[1] or "{}")
except Exception:
    payload = {}

disks = []
for item in payload.get("blockdevices", []):
    if not isinstance(item, dict) or item.get("type") != "disk":
        continue
    path = str(item.get("path") or "").strip()
    if not path or path.startswith(("/dev/loop", "/dev/ram", "/dev/zram", "/dev/sr")):
        continue
    mountpoints = []
    for child in item.get("children") or []:
        if isinstance(child, dict):
            for mp in child.get("mountpoints") or []:
                if mp:
                    mountpoints.append(str(mp))
    disks.append(
        {
            "path": path,
            "name": str(item.get("name") or ""),
            "size": str(item.get("size") or "?"),
            "model": str(item.get("model") or item.get("vendor") or "Unknown").strip() or "Unknown",
            "transport": str(item.get("tran") or ""),
            "removable": str(item.get("rm") or "0") == "1",
            "rotational": str(item.get("rota") or "0") == "1",
            "serial": str(item.get("serial") or ""),
            "mounted_children": mountpoints,
        }
    )

print(json.dumps({"ok": True, "disks": disks}, indent=2, ensure_ascii=True))
PY
}

prepare_log() {
  if [[ "$DRY_RUN" -eq 1 && "$EUID" -ne 0 && "$LOG_FILE" == "/var/log/crixa-installer.log" ]]; then
    LOG_FILE="${XDG_STATE_HOME:-$HOME/.local/state}/crixa-installer/dry-run.log"
  fi
  if ! mkdir -p "$(dirname "$LOG_FILE")" 2>/dev/null || ! touch "$LOG_FILE" 2>/dev/null; then
    LOG_FILE="/tmp/crixa-installer-${UID:-user}.log"
    mkdir -p "$(dirname "$LOG_FILE")"
    touch "$LOG_FILE"
  fi
  chmod 0600 "$LOG_FILE" 2>/dev/null || true
  if [[ "$JSON_OUTPUT" -eq 0 ]]; then
    exec > >(tee -a "$LOG_FILE") 2>&1
  fi
}

confirm_destructive() {
  if [[ "$ASSUME_YES" -eq 1 ]]; then
    return
  fi
  echo
  echo "Dockyard will ERASE all data on: $TARGET_DEV"
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

  local root_source root_parent target_base
  root_source="$(findmnt -n -o SOURCE / 2>/dev/null || true)"
  root_parent="$(lsblk -no PKNAME "$root_source" 2>/dev/null | head -n1 || true)"
  target_base="$(basename "$TARGET_DEV")"
  if [[ -n "$root_parent" && "$root_parent" == "$target_base" ]]; then
    die "Refusing to install over the currently booted root disk: $TARGET_DEV"
  fi

  local mounted_children
  mounted_children="$(lsblk -nr -o MOUNTPOINT "$TARGET_DEV" 2>/dev/null | awk 'NF' || true)"
  if [[ "$DRY_RUN" -eq 0 && -n "$mounted_children" ]]; then
    die "Target has mounted partitions. Unmount them before installing."
  fi

  TARGET_BIOS_GRUB_PART="$(partition_name_by_index 1)"
  TARGET_EFI_PART="$(partition_name_by_index 2)"
  TARGET_ROOT_PART="$(partition_name_by_index 3)"
}

emit_plan() {
  if [[ "$JSON_OUTPUT" -ne 1 ]]; then
    return
  fi
  python3 - "$TARGET_DEV" "$TARGET_BIOS_GRUB_PART" "$TARGET_EFI_PART" "$TARGET_ROOT_PART" "$HOSTNAME_VALUE" "$TARGET_USER" "$TIMEZONE_VALUE" "$ROOT_LABEL" "$DRY_RUN" <<'PY'
import json
import sys

target, bios, efi, root, hostname, user, timezone, label, dry_run = sys.argv[1:10]
print(
    json.dumps(
        {
            "event": "plan",
            "target": target,
            "dry_run": dry_run == "1",
            "hostname": hostname,
            "user": user,
            "timezone": timezone,
            "root_label": label,
            "partitions": [
                {"path": bios, "role": "BIOS boot", "size": "2 MiB"},
                {"path": efi, "role": "EFI system", "size": "512 MiB", "filesystem": "vfat"},
                {"path": root, "role": "CRIXA root", "size": "remaining disk", "filesystem": "ext4"},
            ],
        },
        ensure_ascii=True,
    ),
    flush=True,
)
PY
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

  stage "copy" 55 "Copying live filesystem to target disk"
  if [[ "$DRY_RUN" -eq 1 ]]; then
    log "+ rsync -aHAX --numeric-ids / $TARGET_MOUNT"
    return
  fi

  if [[ "$JSON_OUTPUT" -eq 1 ]]; then
    if ! rsync -aHAX --numeric-ids "${excludes[@]}" / "$TARGET_MOUNT" >> "$LOG_FILE" 2>&1; then
      log "Primary rsync failed, retrying with relaxed metadata flags"
      rsync -aH --numeric-ids "${excludes[@]}" / "$TARGET_MOUNT" >> "$LOG_FILE" 2>&1
    fi
  else
    if ! rsync -aHAX --numeric-ids "${excludes[@]}" / "$TARGET_MOUNT"; then
      log "Primary rsync failed, retrying with relaxed metadata flags"
      rsync -aH --numeric-ids "${excludes[@]}" / "$TARGET_MOUNT"
    fi
  fi
}

configure_installed_system() {
  stage "configure" 74 "Configuring target system"

  local root_uuid
  local efi_uuid
  if [[ "$DRY_RUN" -eq 1 ]]; then
    root_uuid="DRY-RUN-ROOT"
    efi_uuid="DRY-RUN-EFI"
  else
    root_uuid="$(blkid -s UUID -o value "$TARGET_ROOT_PART")"
    efi_uuid="$(blkid -s UUID -o value "$TARGET_EFI_PART")"
    [[ -n "$root_uuid" ]] || die "Failed to get UUID for $TARGET_ROOT_PART"
    [[ -n "$efi_uuid" ]] || die "Failed to get UUID for $TARGET_EFI_PART"
  fi

  write_target_file "etc/fstab" "UUID=$root_uuid / ext4 defaults,noatime 0 1
UUID=$efi_uuid /boot/efi vfat umask=0077 0 1
tmpfs /tmp tmpfs defaults,nosuid,nodev 0 0"
  write_target_file "etc/hostname" "$HOSTNAME_VALUE"
  write_target_file "etc/hosts" "127.0.0.1 localhost
127.0.1.1 $HOSTNAME_VALUE"
  write_target_file "etc/sddm.conf.d/10-crixa.conf" "[General]
DisplayServer=x11

[Theme]
Current=breeze
CursorTheme=breeze_cursors
EnableAvatars=false

[Users]
RememberLastSession=false
RememberLastUser=false"
  write_target_file "etc/sddm.conf.d/20-crixa-autologin.conf" "[Autologin]
User=$TARGET_USER
Session=plasma.desktop
Relogin=false"

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

  stage "bootloader" 86 "Installing bootloader and boot services"
  chroot "$TARGET_MOUNT" /bin/bash -lc "DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends grub-common grub2-common grub-pc-bin grub-efi-amd64-bin || true"
  chroot "$TARGET_MOUNT" /bin/bash -lc "rm -f /etc/lightdm/lightdm.conf.d/50-crixa-autologin.conf || true"
  chroot "$TARGET_MOUNT" /bin/bash -lc "systemctl disable lightdm || true"
  chroot "$TARGET_MOUNT" /bin/bash -lc "systemctl enable NetworkManager bluetooth ModemManager sddm || true"
  chroot "$TARGET_MOUNT" /bin/bash -lc "systemctl set-default graphical.target || true"
  chroot "$TARGET_MOUNT" /bin/bash -lc "update-initramfs -u -k all || true"
  chroot "$TARGET_MOUNT" /bin/bash -lc "grub-install --target=i386-pc '$TARGET_DEV' || true"
  chroot "$TARGET_MOUNT" /bin/bash -lc "grub-install --target=x86_64-efi --efi-directory=/boot/efi --bootloader-id=CRIXA --removable --no-nvram"
  chroot "$TARGET_MOUNT" /bin/bash -lc "update-grub"
}

main() {
  parse_args "$@"

  if [[ "$PROBE_ONLY" -eq 1 ]]; then
    probe_disks
    exit 0
  fi

  prepare_log
  if [[ "$DRY_RUN" -eq 0 && "$VALIDATE_ONLY" -eq 0 ]]; then
    require_root
  fi
  require_cmds
  validate_target

  if [[ "$VALIDATE_ONLY" -eq 1 ]]; then
    emit_plan
    stage "validated" 100 "Target validation passed"
    exit 0
  fi

  stage "start" 4 "Starting Dockyard install"
  log "Target: $TARGET_DEV"
  log "Root partition: $TARGET_ROOT_PART"
  log "EFI partition: $TARGET_EFI_PART"
  log "Hostname: $HOSTNAME_VALUE"
  log "Primary user: $TARGET_USER"
  log "Timezone: $TIMEZONE_VALUE"
  [[ "$DRY_RUN" -eq 1 ]] && log "Dry-run mode enabled"
  emit_plan

  confirm_destructive

  stage "partition" 14 "Preparing disk partitions"
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

  stage "format" 31 "Formatting target filesystems"
  run mkfs.vfat -F 32 -n CRIXA_EFI "$TARGET_EFI_PART"
  run mkfs.ext4 -F -L "$ROOT_LABEL" "$TARGET_ROOT_PART"
  run mkdir -p "$TARGET_MOUNT"
  run mount "$TARGET_ROOT_PART" "$TARGET_MOUNT"
  run mkdir -p "$TARGET_MOUNT/boot/efi"
  run mount "$TARGET_EFI_PART" "$TARGET_MOUNT/boot/efi"

  sync_system
  configure_installed_system

  stage "finish" 96 "Flushing disk writes"
  run sync
  stage "complete" 100 "Install complete. You can reboot and boot from $TARGET_DEV."
  log "Installer log: $LOG_FILE"
}

main "$@"
