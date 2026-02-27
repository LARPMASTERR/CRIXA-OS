#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
PERSIST_IMG="${PERSIST_IMG:-/var/tmp/crixa-os3/CRIXA_OS_v0_persistence.img}"
PERSIST_SIZE="${PERSIST_SIZE:-24G}"
MOUNT_DIR="$PROJECT_ROOT/build/work/persist-mnt"

if [[ "$EUID" -ne 0 ]]; then
  echo "Run as root:"
  echo "  wsl -u root bash -lc 'cd /mnt/c/Users/[USER]/Desktop/OS3 && ./build/prepare-persistence.sh'"
  exit 1
fi

mkdir -p "$(dirname "$PERSIST_IMG")" "$MOUNT_DIR"

if [[ ! -f "$PERSIST_IMG" ]]; then
  echo "Creating persistence image: $PERSIST_IMG ($PERSIST_SIZE)"
  truncate -s "$PERSIST_SIZE" "$PERSIST_IMG"
  mkfs.ext4 -F -L persistence "$PERSIST_IMG" >/dev/null
fi

chmod 0666 "$PERSIST_IMG"

LOOP_DEV="$(losetup --show -f "$PERSIST_IMG")"
cleanup() {
  umount -lf "$MOUNT_DIR" >/dev/null 2>&1 || true
  losetup -d "$LOOP_DEV" >/dev/null 2>&1 || true
}
trap cleanup EXIT

mount "$LOOP_DEV" "$MOUNT_DIR"

if [[ ! -f "$MOUNT_DIR/persistence.conf" ]] || ! grep -q '^/ union$' "$MOUNT_DIR/persistence.conf"; then
  echo "/ union" > "$MOUNT_DIR/persistence.conf"
fi

sync
chmod 0666 "$PERSIST_IMG"
echo "Persistence image ready: $PERSIST_IMG"
