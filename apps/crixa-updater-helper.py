#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ALLOWED_TRACKS = {"stable", "beta", "canary"}


def respond(payload: dict, code: int = 0) -> None:
    print(json.dumps(payload, ensure_ascii=True))
    raise SystemExit(code)


def releasectl_command() -> list[str]:
    executable = shutil.which("crixa-releasectl")
    if executable:
        return [executable]
    local = Path(__file__).resolve().with_name("crixa-releasectl.py")
    if local.exists():
        return [sys.executable, str(local)]
    return ["crixa-releasectl"]


def switch_track(args: argparse.Namespace) -> int:
    if os.geteuid() != 0:
        respond({"ok": False, "error": "Transit helper must run as root"}, 3)
    track = args.track.strip().lower()
    if track not in ALLOWED_TRACKS:
        respond({"ok": False, "error": "unsupported release track"}, 2)
    cmd = releasectl_command() + ["switch-track", track, "--json"]
    result = subprocess.run(cmd, capture_output=True, text=True, check=False, timeout=45)
    stdout = (result.stdout or "").strip()
    stderr = (result.stderr or "").strip()
    if result.returncode != 0:
        respond({"ok": False, "error": stderr or stdout or "track switch failed", "log": [stdout, stderr]}, 1)
    try:
        payload = json.loads(stdout or "{}")
    except json.JSONDecodeError:
        payload = {"message": stdout or "track switched"}
    payload["ok"] = True
    respond(payload)
    return 0


def run_self_test() -> int:
    checks = [
        ("releasectl", shutil.which("crixa-releasectl") is not None or Path(__file__).resolve().with_name("crixa-releasectl.py").exists()),
        ("root mode", os.geteuid() == 0),
    ]
    ok = checks[0][1]
    for name, passed in checks:
        if name == "root mode" and not passed:
            print("warn: root mode - pkexec will run this helper as root for real track changes")
            continue
        print(f"{'ok' if passed else 'fail'}: {name}")
    return 0 if ok else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Privileged Transit release-track helper")
    parser.add_argument("--self-test", action="store_true")
    sub = parser.add_subparsers(dest="action")
    switch = sub.add_parser("switch-track", help="switch CRIXA release track")
    switch.add_argument("track")
    switch.add_argument("--json", action="store_true")
    switch.set_defaults(func=switch_track)
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
