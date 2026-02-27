param(
  [switch]$Headless,
  [string]$Ram = "8G",
  [int]$Smp = 8,
  [string]$Display = "gtk,gl=off,show-tabs=off,zoom-to-fit=off",
  [string]$CpuModel = "",
  [string]$VideoModel = "auto",
  [string]$RequireKvm = "1",
  [string]$PersistEnable = "1",
  [string]$PersistSize = "24G",
  [string]$PersistImage = "/var/tmp/crixa-os3/CRIXA_OS_v0_persistence.img"
)

$ErrorActionPreference = "Stop"

$project = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$projectPosix = $project -replace "\\", "/"
$projectWsl = (wsl wslpath -a "$projectPosix").Trim()
if (-not $projectWsl) {
  throw "Unable to resolve WSL path for project: $project"
}

$arg = ""
if ($Headless) {
  $arg = "--headless"
}

if ($PersistEnable -eq "1") {
  wsl -u root bash -lc "cd '$projectWsl' && chmod +x build/prepare-persistence.sh && PERSIST_SIZE='$PersistSize' PERSIST_IMG='$PersistImage' ./build/prepare-persistence.sh"
}

wsl bash -lc "cd '$projectWsl' && chmod +x build/run-qemu.sh build/test-qemu.sh build/fix-kvm-perms.sh && RAM='$Ram' SMP='$Smp' QEMU_DISPLAY='$Display' CPU_MODEL='$CpuModel' VGA_MODEL='$VideoModel' REQUIRE_KVM='$RequireKvm' PERSIST_ENABLE='$PersistEnable' PERSIST_IMG='$PersistImage' ./build/run-qemu.sh $arg"
