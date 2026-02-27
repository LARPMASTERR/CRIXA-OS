#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
PROJECT_ROOTFS="$PROJECT_ROOT/rootfs"
LINUX_ROOTFS="${LINUX_ROOTFS:-/var/tmp/crixa-os3-build/rootfs}"
EXPORT_TO_PROJECT_ROOTFS="${EXPORT_TO_PROJECT_ROOTFS:-0}"

if [[ "$EUID" -ne 0 ]]; then
  echo "Run as root:"
  echo "  wsl -u root bash -lc 'cd /mnt/c/Users/[USER]/Desktop/OS3 && ./build/refresh-hardware-stack.sh'"
  exit 1
fi

if [[ ! -d "$PROJECT_ROOTFS/etc" ]]; then
  echo "Project rootfs missing at: $PROJECT_ROOTFS"
  echo "Run a full build once first."
  exit 1
fi

if [[ ! -d "$LINUX_ROOTFS/etc" ]]; then
  echo "Linux workspace rootfs missing at: $LINUX_ROOTFS"
  echo "Run a full build once first to seed this workspace rootfs."
  exit 1
fi

echo "Refreshing assets + hardware stack in Linux workspace rootfs: $LINUX_ROOTFS"
ROOTFS_DIR="$LINUX_ROOTFS" SYNC_ENABLE_APT=1 "$SCRIPT_DIR/sync-rootfs.sh"

if [[ "$EXPORT_TO_PROJECT_ROOTFS" == "1" ]]; then
  echo "Exporting Linux workspace rootfs back to project snapshot: $PROJECT_ROOTFS"
  if ! rsync -rlt --delete \
    --no-perms \
    --no-owner \
    --no-group \
    --exclude='dev/*' \
    --exclude='proc/*' \
    --exclude='sys/*' \
    --exclude='run/*' \
    --exclude='tmp/*' \
    "$LINUX_ROOTFS"/ "$PROJECT_ROOTFS"/; then
    echo
    echo "Warning: export to Windows-backed project rootfs failed (likely NTFS case-sensitivity collision)."
    echo "Use Linux workspace rootfs directly for repack/build operations:"
    echo "  ROOTFS_DIR=$LINUX_ROOTFS ./build/repack-iso.sh"
    echo
  fi
else
  echo "Skipping export to project rootfs (EXPORT_TO_PROJECT_ROOTFS=$EXPORT_TO_PROJECT_ROOTFS)"
fi

echo "Hardware stack refresh complete in: $LINUX_ROOTFS"
