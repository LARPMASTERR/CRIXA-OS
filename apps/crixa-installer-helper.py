#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

DEVICE_RE = re.compile(r"^/dev/[A-Za-z0-9._/+:-]+$")
HOST_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9-]{0,62}$")
USER_RE = re.compile(r"^[a-z_][a-z0-9_-]{0,31}$")
LABEL_RE = re.compile(r"^[A-Za-z0-9_.-]{1,32}$")
TIMEZONE_RE = re.compile(r"^[A-Za-z0-9_+./-]{1,80}$")


def respond(payload: dict, code: int = 0) -> None:
    print(json.dumps(payload, ensure_ascii=True))
    raise SystemExit(code)


def installer_command() -> list[str]:
    installed = Path("/usr/local/sbin/crixa-install")
    if installed.exists():
        return [str(installed)]
    local = Path(__file__).resolve().with_name("crixa-install.sh")
    if local.exists():
        if os.access(local, os.X_OK):
            return [str(local)]
        return ["bash", str(local)]
    return ["crixa-install"]


def validate_target(target: str) -> str:
    if not DEVICE_RE.match(target):
        raise RuntimeError("target must be a /dev disk path")
    if not Path(target).exists():
        raise RuntimeError("target device does not exist")
    result = subprocess.run(["lsblk", "-dn", "-o", "TYPE", target], capture_output=True, text=True, check=False)
    if result.returncode != 0 or result.stdout.strip() != "disk":
        raise RuntimeError("target must be a whole disk")
    return target


def validate_args(args: argparse.Namespace) -> None:
    validate_target(args.target)
    if not HOST_RE.match(args.hostname):
        raise RuntimeError("invalid hostname")
    if not USER_RE.match(args.user):
        raise RuntimeError("invalid user name")
    if not LABEL_RE.match(args.label):
        raise RuntimeError("invalid filesystem label")
    if not TIMEZONE_RE.match(args.timezone):
        raise RuntimeError("invalid timezone")
    if "\x00" in (args.user_password or ""):
        raise RuntimeError("invalid password")


def run_install(args: argparse.Namespace) -> int:
    if os.geteuid() != 0:
        respond({"ok": False, "error": "installer helper must run as root"}, 3)
    try:
        validate_args(args)
    except Exception as exc:
        respond({"ok": False, "error": str(exc)}, 2)

    cmd = installer_command()
    cmd += [
        "--target",
        args.target,
        "--hostname",
        args.hostname,
        "--user",
        args.user,
        "--label",
        args.label,
        "--timezone",
        args.timezone,
        "--yes",
        "--json",
    ]
    if args.log:
        cmd += ["--log", args.log]
    if args.user_password:
        cmd += ["--user-password", args.user_password]
    os.execvp(cmd[0], cmd)
    return 1


def run_self_test() -> int:
    checks: list[tuple[str, bool, str]] = []
    command = installer_command()
    checks.append(("installer backend", shutil.which(command[0]) is not None or Path(command[0]).exists(), "crixa-install backend found"))
    checks.append(("lsblk", shutil.which("lsblk") is not None, "lsblk available"))
    checks.append(("root mode", os.geteuid() == 0, "helper is running as root"))
    ok = all(item[1] for item in checks[:2])
    for name, passed, message in checks:
        state = "ok" if passed else ("warn" if name == "root mode" else "fail")
        print(f"{state}: {name} - {message}")
    return 0 if ok else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Privileged Dockyard install helper")
    parser.add_argument("--self-test", action="store_true")
    sub = parser.add_subparsers(dest="action")

    install = sub.add_parser("install", help="run a validated full-disk install")
    install.add_argument("--target", required=True)
    install.add_argument("--hostname", default="crixa-os")
    install.add_argument("--user", default="crixa")
    install.add_argument("--user-password", default="")
    install.add_argument("--label", default="CRIXA_ROOT")
    install.add_argument("--timezone", default="UTC")
    install.add_argument("--log", default="/var/log/crixa-installer.log")
    install.set_defaults(func=run_install)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    if args.self_test:
        return run_self_test()
    if not hasattr(args, "func"):
        parser.print_help()
        return 2
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
