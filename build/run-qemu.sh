#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [[ "${1:-}" == "--headless" ]]; then
  exec "$SCRIPT_DIR/test-qemu.sh" --headless
fi

if [[ "$(id -u)" -eq 0 ]]; then
  echo "Running QEMU GUI as root in WSLg can trigger GDK seat warnings."
  echo "Use a normal user for GUI mode when possible."
fi

if [[ -e /dev/kvm && ( ! -r /dev/kvm || ! -w /dev/kvm ) ]]; then
  echo "Warning: /dev/kvm exists but this user cannot access it."
  echo "QEMU will run without hardware acceleration and feel slow."
  echo "Fix once: sudo $SCRIPT_DIR/fix-kvm-perms.sh $(id -un)"
fi

if [[ ! -e /dev/kvm ]]; then
  echo "Warning: /dev/kvm is not present in this WSL session."
  echo "QEMU will use software emulation (TCG), which can cause low FPS and input delay."
fi

if [[ "${PERSIST_ENABLE:-1}" == "1" && ! -f "${PERSIST_IMG:-/var/tmp/crixa-os3/CRIXA_OS_v0_persistence.img}" ]]; then
  echo "Tip: persistence image missing. Create once as root:"
  echo "  $SCRIPT_DIR/prepare-persistence.sh"
fi

echo "Launching with RAM=${RAM:-8G} SMP=${SMP:-8} DISPLAY=${QEMU_DISPLAY:-gtk,gl=off,show-tabs=off,zoom-to-fit=off} VIDEO=${VGA_MODEL:-auto} REQUIRE_KVM=${REQUIRE_KVM:-1} PERSIST=${PERSIST_ENABLE:-1}"
exec "$SCRIPT_DIR/test-qemu.sh"
