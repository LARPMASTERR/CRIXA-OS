#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
ISO_PATH="$PROJECT_ROOT/iso/CRIXA_OS_v0.iso"
LOG_DIR="$PROJECT_ROOT/logs"
TIMESTAMP="$(date +%Y%m%d-%H%M%S)"
QEMU_LOG="$LOG_DIR/qemu-boot-$TIMESTAMP.log"
RAM="${RAM:-8G}"
SMP="${SMP:-8}"
QEMU_DISPLAY="${QEMU_DISPLAY:-gtk,gl=off,show-tabs=off,zoom-to-fit=off}"
VGA_MODEL="${VGA_MODEL:-auto}"
ACCEL_MODE="tcg,thread=multi,tb-size=1024"
CPU_MODEL="${CPU_MODEL:-}"
REQUIRE_KVM="${REQUIRE_KVM:-1}"
KVM_OK=0
PERSIST_ENABLE="${PERSIST_ENABLE:-1}"
PERSIST_IMG="${PERSIST_IMG:-/var/tmp/crixa-os3/CRIXA_OS_v0_persistence.img}"

mkdir -p "$LOG_DIR"

if [[ ! -f "$ISO_PATH" ]]; then
  echo "ISO not found: $ISO_PATH"
  exit 1
fi

if ! command -v qemu-system-x86_64 >/dev/null 2>&1; then
  echo "qemu-system-x86_64 is not installed on this host."
  echo "Install it, then rerun $0."
  exit 1
fi

HEADLESS=0
if [[ "${1:-}" == "--headless" ]]; then
  HEADLESS=1
fi

CMD=(
  qemu-system-x86_64
  -machine q35,vmport=off
  -m "$RAM"
  -smp "$SMP"
  -cdrom "$ISO_PATH"
  -boot d
  -device qemu-xhci
  -device usb-kbd
  -device usb-tablet
  -nic user,model=virtio-net-pci
)

if [[ -e /dev/kvm && -r /dev/kvm && -w /dev/kvm ]]; then
  KVM_OK=1
  if [[ -z "$CPU_MODEL" ]]; then
    CPU_MODEL="host"
  fi
  CMD+=(-accel kvm)
  ACCEL_MODE="kvm"
else
  if [[ -z "$CPU_MODEL" ]]; then
    CPU_MODEL="qemu64"
  fi
  CMD+=(-accel tcg,thread=multi,tb-size=1024)
fi

if [[ "$KVM_OK" -ne 1 && "$REQUIRE_KVM" == "1" && "$HEADLESS" -eq 0 ]]; then
  echo "KVM acceleration is required for acceptable GUI performance."
  echo "Current mode would be TCG software emulation (very slow)."
  echo "Fix once: sudo $PROJECT_ROOT/build/fix-kvm-perms.sh $(id -un)"
  echo "Then restart WSL from Windows PowerShell: wsl --shutdown"
  echo "If you still want slow TCG mode, run with REQUIRE_KVM=0."
  exit 2
fi

if [[ "$VGA_MODEL" == "auto" ]]; then
  if [[ "$QEMU_DISPLAY" == *"gl=on"* ]]; then
    VGA_MODEL="virtio-vga-gl"
  else
    VGA_MODEL="virtio-vga"
  fi
fi

case "$VGA_MODEL" in
  virtio-vga|virtio-vga-gl|virtio-gpu|virtio-gpu-gl|qxl|qxl-vga)
    CMD+=(-device "$VGA_MODEL")
    ;;
  *)
    CMD+=(-vga "$VGA_MODEL")
    ;;
esac

if [[ "$PERSIST_ENABLE" == "1" ]]; then
  if [[ -f "$PERSIST_IMG" ]]; then
    CMD+=(-drive "if=virtio,format=raw,file=$PERSIST_IMG")
  else
    echo "Persistence image not found: $PERSIST_IMG"
    echo "Create it once as root: $PROJECT_ROOT/build/prepare-persistence.sh"
  fi
fi

CMD+=(-cpu "$CPU_MODEL")

if [[ "$HEADLESS" -eq 1 ]]; then
  CMD+=(-display none -serial "file:$QEMU_LOG" -no-reboot)
else
  CMD+=(-display "$QEMU_DISPLAY" -serial "file:$QEMU_LOG")
fi

echo "Running: ${CMD[*]}"
echo "Acceleration: $ACCEL_MODE"
echo "CPU model: $CPU_MODEL"
echo "Video model: $VGA_MODEL"
echo "RAM: $RAM  SMP: $SMP"
if [[ "$ACCEL_MODE" != "kvm" && -e /dev/kvm ]]; then
  echo "Tip: /dev/kvm exists but is not accessible by current user."
  echo "Run once as root: $PROJECT_ROOT/build/fix-kvm-perms.sh $(id -un)"
fi
set +e
"${CMD[@]}" 2>&1 | tee -a "$QEMU_LOG"
QEMU_EXIT="${PIPESTATUS[0]}"
set -e

if [[ "$QEMU_EXIT" -ne 0 && "$QEMU_DISPLAY" == *"gl=on"* ]]; then
  if grep -qi "opengl is not available" "$QEMU_LOG"; then
    echo "QEMU OpenGL backend is unavailable in this environment."
    echo "Rerun with: QEMU_DISPLAY='gtk,gl=off,show-tabs=off,zoom-to-fit=off'"
  fi
fi

echo "QEMU log: $QEMU_LOG"
exit "$QEMU_EXIT"
