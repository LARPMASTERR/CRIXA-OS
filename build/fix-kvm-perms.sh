#!/usr/bin/env bash
set -Eeuo pipefail

is_wsl() {
  grep -qiE "(microsoft|wsl)" /proc/version /proc/sys/kernel/osrelease 2>/dev/null
}

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Run as root. Example:"
  echo "  cd $(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd) && sudo ./build/fix-kvm-perms.sh [USER]"
  exit 1
fi

TARGET_USER="${1:-${SUDO_USER:-}}"
if [[ -z "$TARGET_USER" ]]; then
  echo "Usage: $0 <username>"
  exit 1
fi

if ! id "$TARGET_USER" >/dev/null 2>&1; then
  echo "User not found: $TARGET_USER"
  exit 1
fi

KVM_DEV_GID=""
if [[ -e /dev/kvm ]]; then
  KVM_DEV_GID="$(stat -c '%g' /dev/kvm 2>/dev/null || true)"
fi

if getent group kvm >/dev/null 2>&1; then
  CURRENT_KVM_GID="$(getent group kvm | cut -d: -f3)"
else
  CURRENT_KVM_GID=""
fi

if [[ -n "$KVM_DEV_GID" && -n "$CURRENT_KVM_GID" && "$CURRENT_KVM_GID" != "$KVM_DEV_GID" ]]; then
  if getent group "$KVM_DEV_GID" >/dev/null 2>&1; then
    EXISTING_GROUP="$(getent group "$KVM_DEV_GID" | cut -d: -f1)"
    echo "kvm group GID ($CURRENT_KVM_GID) does not match /dev/kvm GID ($KVM_DEV_GID)."
    echo "GID $KVM_DEV_GID is already owned by group: $EXISTING_GROUP"
    echo "Resolve that conflict first, then rerun this script."
    exit 1
  fi
  groupmod -g "$KVM_DEV_GID" kvm
elif [[ -z "$CURRENT_KVM_GID" ]]; then
  if [[ -n "$KVM_DEV_GID" ]] && ! getent group "$KVM_DEV_GID" >/dev/null 2>&1; then
    groupadd -g "$KVM_DEV_GID" kvm
  else
    groupadd -f kvm
  fi
fi

usermod -aG kvm "$TARGET_USER"
chgrp kvm /dev/kvm 2>/dev/null || true
chmod 660 /dev/kvm 2>/dev/null || true
chgrp kvm /dev/vhost-net 2>/dev/null || true
chmod 660 /dev/vhost-net 2>/dev/null || true
chgrp kvm /dev/vhost-vsock 2>/dev/null || true
chmod 660 /dev/vhost-vsock 2>/dev/null || true

echo "Added $TARGET_USER to group: kvm"
if is_wsl; then
  echo "Now restart WSL so group membership is refreshed:"
  echo "  powershell.exe -Command \"wsl --shutdown\""
  echo "Then verify in a new WSL shell:"
else
  echo "Now refresh group membership by logging out and back in, rebooting, or running:"
  echo "  newgrp kvm"
  echo "Then verify in that refreshed shell:"
fi
echo "  id -nG | tr ' ' '\\n' | grep '^kvm$' && echo KVM_READY"
