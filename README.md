# CRIXA OS Wiki

CRIXA OS is a custom live Linux distribution project built in `OS3/` around a modular desktop stack, automated image generation, and rapid iteration inside WSL + QEMU. This document is intended to be the canonical operational wiki for the repository: how to build, how the system boots, where each subsystem is configured, and how to safely evolve the OS without destabilizing it.

This is not a generic Linux guide. It is a project-level system map and runbook for the exact CRIXA toolchain in this repository.

## Legal and Publishing

- Source license: [`LICENSE`](LICENSE) (MIT)
- Third-party notices: [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md)
- Distribution/legal policy: [`LEGAL.md`](LEGAL.md)
- Security/reporting policy: [`SECURITY.md`](SECURITY.md)
- Generated artifacts (`rootfs/`, `iso/`, `logs/`, `build/work/`, `crixa-repo/`) are local build outputs and are intentionally excluded from source control.

## 1) What CRIXA OS Is

CRIXA OS v0 is a Debian-based live operating system image (`CRIXA_OS_v0.iso`) designed to:

- boot in QEMU
- auto-login to a desktop session
- launch a visual environment with taskbar/panel
- provide launcher, terminal, file manager, browser, settings, and system monitor workflows
- support persistent state via a dedicated persistence disk image

The build approach is layered and script-driven. You are not hand-editing random rootfs files in ad hoc ways. You are working through defined integration scripts so changes can be repeated and re-packed reliably.

## 2) Current Architecture

CRIXA is composed of:

1. Base OS and kernel
- Debian root filesystem generated in local build workspace and exported to `rootfs/` for local iteration
- Linux kernel + initrd included in live ISO staging

2. Boot and live entry
- GRUB config in `boot/grub.cfg`
- live-boot kernel args include `persistence`, `quiet`, `splash`, and CRIXA hostname/user defaults

3. Login and session
- LightDM autologin into user `crixa`
- Openbox session startup

4. UI stack
- Window manager: Openbox
- Panel/taskbar: tint2
- Launcher/menu: rofi + custom CRIXA scripts
- Terminal: Alacritty with xterm fallback
- File manager: Thunar
- Browser: Firefox ESR wrapper
- Settings: custom CRIXA Control Center (`apps/crixa-settings.py`)
- Task manager: custom CRIXA task monitor (`apps/crixa-task-manager.py`)

5. Theming and identity
- CRIXA theme assets under `themes/CRIXA`
- shell/UI configs under `ui-shell`
- wallpapers/icons under `assets`

## 3) Repository Layout (Operational Meaning)

`apps/`
- user-facing app launchers/wrappers and custom utilities (`crixa-settings`, `crixa-task-manager`, `crixa-wallpaper`, `crixa-fetch`, etc.)

`assets/`
- wallpapers, icons, fonts used in live image branding

`boot/`
- GRUB boot menu and kernel parameters for live boot

`build/`
- all build and runtime orchestration scripts
- full build (`build.sh`), fast repack (`repack-iso.sh`), rootfs sync (`sync-rootfs.sh`), QEMU runner scripts, persistence prep, KVM permission fixups

`iso/`
- final output image: `CRIXA_OS_v0.iso`

`logs/`
- build logs, package install logs, repack logs, QEMU boot logs, debug artifacts

`rootfs/`
- project-side root filesystem snapshot used by repack path

`themes/CRIXA/`
- CRIXA Openbox and GTK style definitions

`ui-shell/`
- Openbox/tint2/rofi/X settings and shell snippets used by sync/build pipelines

## 4) Build Modes: Full Build vs Fast Repack

CRIXA has two primary build loops. Use the right one.

### A) Full Build (slow, complete regeneration)

Use when:
- boot chain is broken
- base package set changed significantly
- rootfs needs a clean regenerate from debootstrap
- you need to prove reproducibility from scratch

Command:

```bash
wsl -u root bash -lc 'cd /mnt/c/Users/[USER]/Desktop/OS3 && ./build/build.sh'
```

What it does:
- installs host build dependencies
- re-bootstrap Debian rootfs
- chroot package installs (desktop stack + dependencies)
- installs CRIXA assets/configs/apps into rootfs
- generates squashfs live filesystem
- stages GRUB payload
- builds final ISO with xorriso

### B) Fast Repack (preferred for most UI/app changes)

Use when:
- editing app scripts
- editing Openbox/tint2/rofi/theme configs
- changing wallpapers/icons
- changing behavior already represented in `rootfs/` + sync scripts

Command:

```bash
wsl -u root bash -lc 'cd /mnt/c/Users/[USER]/Desktop/OS3 && ./build/repack-iso.sh'
```

What it does:
- syncs repo-managed assets/configs/apps into project rootfs
- regenerates live squashfs
- re-stages GRUB and rebuilds ISO

This is much faster than full build and should be your default loop for most feature work.

## 5) QEMU Launch and Runtime Validation

### Recommended launch (PowerShell wrapper)

```powershell
.\build\run-qemu.ps1
```

Defaults:
- RAM `8G`
- SMP `8`
- display `gtk,gl=off,show-tabs=off,zoom-to-fit=off`
- persistence enabled by default

### Parameterized launch examples

```powershell
.\build\run-qemu.ps1 -Ram "8G" -Smp 8 -Display "gtk,gl=off,show-tabs=off,zoom-to-fit=off"
.\build\run-qemu.ps1 -PersistEnable "0"
.\build\run-qemu.ps1 -Headless
```

### Direct Linux-side launch

```bash
wsl bash -lc 'cd /mnt/c/Users/[USER]/Desktop/OS3 && RAM=8G SMP=8 ./build/run-qemu.sh'
```

### Performance and KVM

CRIXA runner scripts strongly prefer KVM acceleration. Without KVM, QEMU falls back to TCG software emulation and GUI responsiveness drops heavily.

Fix KVM access once:

```bash
wsl -u root bash -lc 'cd /mnt/c/Users/[USER]/Desktop/OS3 && ./build/fix-kvm-perms.sh [USER]'
powershell.exe -Command "wsl --shutdown"
```

Then reopen WSL and verify:

```bash
id -nG | tr " " "\n" | grep "^kvm$" && echo KVM_READY
```

## 6) Persistence Model

CRIXA supports persistence with an external disk image mounted as a virtio drive in QEMU.

Prepare persistence image:

```bash
wsl -u root bash -lc 'cd /mnt/c/Users/[USER]/Desktop/OS3 && ./build/prepare-persistence.sh'
```

Defaults:
- image path: `/var/tmp/crixa-os3/CRIXA_OS_v0_persistence.img`
- size: `24G`
- filesystem label: `persistence`
- `persistence.conf`: `/ union`

Kernel parameters already include `persistence` in `boot/grub.cfg`, so when the persistence image is attached, state changes can survive reboot.

## 6.1) Bare Metal + Rufus Flow

CRIXA images are now built as hybrid BIOS + UEFI ISOs (El Torito entries for both), which makes them suitable for direct USB flashing via Rufus.

### Build/repack before flashing

```bash
wsl -u root bash -lc 'cd /mnt/c/Users/[USER]/Desktop/OS3 && ./build/repack-iso.sh'
```

Output ISO:
- `iso/CRIXA_OS_v0.iso`

### Rufus recommended settings

1. Device: select your target USB.
2. Boot selection: `iso/CRIXA_OS_v0.iso`.
3. Partition scheme: `GPT` (preferred for modern UEFI systems).
4. Target system: `UEFI (non CSM)` when available.
5. Image mode prompt: choose `DD Image mode` for the most consistent hybrid-ISO behavior.

### Bare-metal validation checklist

After booting CRIXA from USB:

```bash
nmcli device status
bluetoothctl show
pactl info
glxinfo -B | head -n 20
vulkaninfo --summary | head -n 30
```

Expected:
- network adapters visible in `nmcli`
- Bluetooth controller present (if hardware exists)
- PipeWire/Pulse audio server reported by `pactl`
- OpenGL/Vulkan renderer info present

If a GPU has compatibility issues, use the GRUB entry:
- `CRIXA OS v0 (Live, Safe Graphics)`

### Disk install note

`crixa-install` now prepares GPT with BIOS boot partition + EFI partition + root partition and installs GRUB for both BIOS and UEFI paths.
This remains an advanced/destructive action; test on non-critical hardware first.

## 6.2) Driver Baseline (NVIDIA + AMD Ready)

CRIXA rootfs now ships with a hardware baseline intended to boot cleanly on common NVIDIA GPU and AMD CPU/GPU systems out of the box.

Required baseline in the image:

- kernel + headers + dkms:
  - `linux-image-amd64`
  - `linux-headers-amd64`
  - `dkms`
- firmware:
  - `firmware-linux`
  - `firmware-linux-nonfree`
  - `firmware-amd-graphics`
  - `firmware-nvidia-gsp`
- graphics drivers:
  - `nvidia-driver`
  - `nvidia-vulkan-icd`
  - `nvidia-smi`
  - `nvidia-settings`
  - `mesa-vulkan-drivers`
  - `xserver-xorg-video-all`
  - `xserver-xorg-input-all`

Networking/Bluetooth/Audio baseline:

- `network-manager`, `wpasupplicant`, `modemmanager`, `usb-modeswitch`
- `bluez`, `blueman`
- `pipewire`, `pipewire-pulse`, `wireplumber`, `alsa-utils`, `pavucontrol`

Fast refresh command (recommended while iterating):

```bash
wsl -u root bash -lc 'cd /mnt/c/Users/[USER]/Desktop/OS3 && EXPORT_TO_PROJECT_ROOTFS=0 ./build/refresh-hardware-stack.sh'
```

Then repack directly from the Linux workspace rootfs:

```bash
wsl -u root bash -lc 'cd /mnt/c/Users/[USER]/Desktop/OS3 && ROOTFS_DIR=/var/tmp/crixa-os3-build/rootfs ./build/repack-iso.sh'
```

## 6.3) Signed System Rollout Channels

CRIXA now includes a signed rollout metadata path for future OS updates.

Source of truth:

- track definitions: `store-packages/system-rollouts.json`
- generated + signed metadata:
  - `crixa-repo/metadata/system-updates.json`
  - `crixa-repo/metadata/system-updates.sig`

Signing flow:

```bash
wsl -u root bash -lc 'cd /mnt/c/Users/[USER]/Desktop/OS3 && ./build/build-crixa-repo.sh'
```

Runtime CLI in CRIXA:

- verify signatures:
  - `crixa-releasectl verify`
- inspect eligibility:
  - `crixa-releasectl status`
- switch channel:
  - `sudo crixa-releasectl switch-track stable`
  - `sudo crixa-releasectl switch-track beta`
  - `sudo crixa-releasectl switch-track canary`
- set local release marker after an applied OS update:
  - `sudo crixa-releasectl set-version 0.0.1 --build-id 20260227-001`

Updater UI integration:

- `CRIXA Updater` now exposes channel buttons and current rollout eligibility state using `crixa-releasectl`.

## 7) Boot and Startup Pipeline

The boot path is intentionally scoped:

1. GRUB menu from `boot/grub.cfg`
2. kernel + initrd from live payload
3. live-boot mounts live filesystem
4. LightDM autologin into `crixa`
5. Openbox session starts
6. `ui-shell/autostart` initializes display mode, wallpaper, panel, and applets

### Startup splash behavior

CRIXA startup splash is driven by Plymouth (`splash` kernel arg + plymouth theme in initramfs). This is boot-stage only and should not override desktop theming.

Important principle:
- boot splash should reduce dead-black time while loading
- it should not replace session wallpaper/taskbar/theme once X/Openbox is active

## 8) UI and Interaction Stack

### Openbox
- window movement, decorations, session behavior
- configs in `ui-shell/rc.xml` and theme in `themes/CRIXA/openbox-themerc`

### tint2
- taskbar, tray, clock, app launch area
- config in `ui-shell/tint2rc`

### rofi
- launcher menus and prompts
- config in `ui-shell/rofi.rasi`

### wallpaper handling
- managed by `apps/crixa-wallpaper.sh`
- state file tracks selected wallpaper
- supports `apply-current`, `next`, `prev`, `random`, `status`, `list`

### CRIXA Control Center
- launcher: `crixa-settings` -> Python app
- code: `apps/crixa-settings.py`
- module pages:
  - Display
  - Appearance
  - Panel
  - Startup
  - Applications
  - System
  - About

## 9) Application Wrappers (What They Do)

`crixa-terminal`
- prefers Alacritty
- xterm fallback for VM compatibility edge cases

`crixa-browser`
- wraps Firefox ESR launch behavior and project preferences

`crixa-files`
- wraps Thunar launch

`crixa-menu`
- launcher shortcut wrapper

`crixa-task-manager`
- opens CRIXA live system monitor script

`crixa-fetch` + `neofetch` shim
- CRIXA identity system card for terminal sessions
- shell snippet in `ui-shell/bashrc-crixa-snippet`

## 10) Theming and Branding Workflow

Primary file touch points:

- GTK theme: `themes/CRIXA/gtk.css`
- Openbox theme: `themes/CRIXA/openbox-themerc`
- launcher style: `ui-shell/rofi.rasi`
- panel style: `ui-shell/tint2rc`
- wallpaper assets: `assets/wallpapers/*`
- icons: `assets/icons/*`

Apply them to ISO:

```bash
wsl -u root bash -lc 'cd /mnt/c/Users/[USER]/Desktop/OS3 && ./build/repack-iso.sh'
```

## 11) Daily Developer Workflow (Recommended)

1. Edit code/config in repo (`apps`, `ui-shell`, `themes`, `assets`, `boot`).
2. For UI/app changes, run fast repack.
3. Boot in QEMU with KVM.
4. Validate:
   - desktop auto-load
   - panel visible and scaled correctly
   - launcher works by mouse clicks
   - settings open and apply state changes
   - terminal, files, browser launch
5. Inspect logs if needed under `logs/`.
6. Only use full build when fast repack cannot represent your change cleanly.

## 12) Troubleshooting Playbook

### Problem: QEMU GTK seat assertion spam / no usable window

Symptoms:
- `Gdk: gdk_seat_get_keyboard` assertion lines
- GUI launch weirdness from root session

Actions:
- launch QEMU as non-root user for GUI mode
- keep root only for build/repack scripts
- use `run-qemu.ps1` wrapper from normal PowerShell user context

### Problem: Very low FPS, stutter, large input delay

Likely cause:
- running without KVM acceleration

Actions:
- check `/dev/kvm` access
- run `build/fix-kvm-perms.sh`
- restart WSL (`wsl --shutdown`)
- relaunch with default KVM-required settings

### Problem: Changes not appearing after edit

Likely cause:
- edited repo files but did not sync/repack

Actions:
- run `build/repack-iso.sh`
- verify generated timestamp in `logs/repack-*.log`
- ensure you are booting latest `iso/CRIXA_OS_v0.iso`

### Problem: Desktop boots but black/blank transitions feel broken

Actions:
- verify wallpaper apply logic in `ui-shell/autostart`
- verify X mode selection logic from xrandr block
- confirm boot splash (`splash` + plymouth) is configured

### Problem: Persistence not saving across reboots

Actions:
- confirm persistence image exists
- verify QEMU command includes persistence drive
- verify `boot/grub.cfg` kernel args include `persistence`
- check image contains `persistence.conf` with `/ union`

## 13) Logging and Observability

CRIXA generates logs in `logs/`:

- `build-*.log`: full build process
- `package-install-*.log`: chroot package install details
- `repack-*.log`: fast repack runs
- `qemu-boot-*.log`: runtime VM serial/debug output
- `build-failures.log`: summarized failure entries

Operational rule:
- do not debug by guessing first
- inspect latest relevant log and correlate timestamp with last action

## 14) Safety Rules for Editing

1. Prefer editing source-of-truth repo files, not ad hoc files inside running VM.
2. Keep changes modular and scoped:
- app behavior in `apps/`
- UI shell in `ui-shell/`
- theme identity in `themes/CRIXA/`
3. Use fast repack for iterative cycles; avoid unnecessary full rebuilds.
4. Do not hard-reset unrelated work in the tree.
5. Preserve boot chain stability:
- avoid unnecessary changes to `boot/grub.cfg`
- keep kernel args intentional and minimal

## 15) Extending CRIXA Cleanly

### Add a new app

1. Add script/launcher in `apps/`.
2. Add `.desktop` entry if it belongs in launcher menus.
3. Wire install into:
- `build/sync-rootfs.sh`
- `build/build.sh`
4. Repack and test.

### Add a new startup service/behavior

1. Prefer Openbox autostart for user-session behavior.
2. For true boot-stage behavior, use initramfs/systemd-level integration with care.
3. Keep startup visual flow lightweight to avoid perceived lag.

### Add new visual assets

1. Drop assets into `assets/wallpapers` or `assets/icons`.
2. Ensure sync/build scripts install them.
3. If user-facing selection is needed, expose via `crixa-wallpaper` or Control Center page.

## 16) Operational Command Reference

### Full build

```bash
wsl -u root bash -lc 'cd /mnt/c/Users/[USER]/Desktop/OS3 && ./build/build.sh'
```

### Fast repack

```bash
wsl -u root bash -lc 'cd /mnt/c/Users/[USER]/Desktop/OS3 && ./build/repack-iso.sh'
```

### Sync rootfs only

```bash
wsl -u root bash -lc 'cd /mnt/c/Users/[USER]/Desktop/OS3 && ./build/sync-rootfs.sh'
```

### Refresh hardware stack (ext4 workspace + export back)

```bash
wsl -u root bash -lc 'cd /mnt/c/Users/[USER]/Desktop/OS3 && ./build/refresh-hardware-stack.sh'
```

### Run VM from PowerShell

```powershell
.\build\run-qemu.ps1
```

### Run VM headless

```powershell
.\build\run-qemu.ps1 -Headless
```

### Prepare persistence image

```bash
wsl -u root bash -lc 'cd /mnt/c/Users/[USER]/Desktop/OS3 && ./build/prepare-persistence.sh'
```

### Fix KVM permissions

```bash
wsl -u root bash -lc 'cd /mnt/c/Users/[USER]/Desktop/OS3 && ./build/fix-kvm-perms.sh [USER]'
```

## 17) Known Constraints

- This is still primarily a live ISO workflow; disk install exists but should be treated as experimental.
- Behavior can differ between:
  - WSLg GUI launch
  - native Linux host QEMU
  - environments with/without KVM
- Performance quality is heavily tied to hardware acceleration and display mode choices.
- Some rootfs symbolic links and metadata look odd from Windows filesystem views; prefer WSL tools for low-level checks.

## 18) CRIXA Design Intent (Project Principles)

CRIXA should feel deliberate, not cobbled together:

- keep interaction mouse-first where expected
- avoid fragmented menu layers and placeholder UX
- make startup coherent (splash to desktop without visual dead zones)
- optimize first for reliable responsiveness in QEMU/KVM
- preserve modularity so future kernel/package-manager/compositor work can be layered without rewriting everything

This wiki should evolve with the system. If a command/path/behavior changes, update this file in the same change set so operational knowledge does not drift from implementation.

---

If you are onboarding new contributors, start them with sections 3, 4, 5, 11, and 12 first. That path gives enough context to build, boot, iterate, and debug CRIXA without accidental regression loops.

CRIXA OS is an experimental operating system project. It is not intended for production, safety-critical, medical, financial, or enterprise use.