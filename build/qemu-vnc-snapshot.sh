#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
ISO_PATH="$PROJECT_ROOT/iso/CRIXA_OS_v0.iso"
LOG_DIR="$PROJECT_ROOT/logs"
VNC_DISPLAY="${VNC_DISPLAY:-1}"
VNC_PORT="$((5900 + VNC_DISPLAY))"
PID_FILE="/tmp/crixa-qemu-vnc.pid"
SERIAL_LOG="$LOG_DIR/qemu-vnc-serial.log"
SNAP1="$LOG_DIR/qemu-snap-1.png"
SNAP2="$LOG_DIR/qemu-snap-2.png"
SNAP3="$LOG_DIR/qemu-snap-3.png"

if [[ ! -f "$ISO_PATH" ]]; then
  echo "Missing ISO: $ISO_PATH"
  exit 1
fi

if ! command -v qemu-system-x86_64 >/dev/null 2>&1; then
  echo "Missing qemu-system-x86_64"
  exit 1
fi

if ! command -v vncsnapshot >/dev/null 2>&1; then
  echo "Missing vncsnapshot"
  exit 1
fi

mkdir -p "$LOG_DIR"
rm -f "$PID_FILE" "$SNAP1" "$SNAP2" "$SNAP3" "$SERIAL_LOG"

cleanup() {
  if [[ -f "$PID_FILE" ]]; then
    kill "$(cat "$PID_FILE")" >/dev/null 2>&1 || true
    rm -f "$PID_FILE"
  fi
}
trap cleanup EXIT

qemu-system-x86_64 \
  -machine q35 \
  -m 4G \
  -smp 4 \
  -cpu max \
  -cdrom "$ISO_PATH" \
  -boot d \
  -display none \
  -vnc "127.0.0.1:$VNC_DISPLAY" \
  -device qemu-xhci \
  -device usb-kbd \
  -device usb-tablet \
  -vga std \
  -serial "file:$SERIAL_LOG" \
  -monitor none \
  -no-reboot \
  -daemonize \
  -pidfile "$PID_FILE"

echo "QEMU PID: $(cat "$PID_FILE")"
echo "Capturing VNC snapshots on display :$VNC_DISPLAY (tcp $VNC_PORT)"

sleep 30
vncsnapshot -allowblank "127.0.0.1:$VNC_DISPLAY" "$SNAP1"
sleep 60
vncsnapshot -allowblank "127.0.0.1:$VNC_DISPLAY" "$SNAP2"
sleep 90
vncsnapshot -allowblank "127.0.0.1:$VNC_DISPLAY" "$SNAP3"

echo "Snapshots saved:"
echo "  $SNAP1"
echo "  $SNAP2"
echo "  $SNAP3"
