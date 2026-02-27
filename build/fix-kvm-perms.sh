#!/usr/bin/env bash
set -Eeuo pipefail

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Run as root. Example:"
  echo "  wsl -u root bash -lc 'cd /mnt/c/Users/[USER]/Desktop/OS3 && ./build/fix-kvm-perms.sh [WSL_USER]'"
  exit 1
fi

TARGET_USER="${1:-${SUDO_USER:-}}"
if [[ -z "$TARGET_USER" ]]; then
  echo "Usage: $0 <wsl-username>"
  exit 1
fi

if ! id "$TARGET_USER" >/dev/null 2>&1; then
  echo "User not found: $TARGET_USER"
  exit 1
fi

groupadd -f kvm
usermod -aG kvm "$TARGET_USER"
chgrp kvm /dev/kvm 2>/dev/null || true
chmod 660 /dev/kvm 2>/dev/null || true

echo "Added $TARGET_USER to group: kvm"
echo "Now restart WSL so group membership is refreshed:"
echo "  powershell.exe -Command \"wsl --shutdown\""
echo "Then verify in a new WSL shell:"
echo "  id -nG | tr ' ' '\\n' | grep '^kvm$' && echo KVM_READY"
