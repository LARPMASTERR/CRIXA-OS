#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import signal
import sys
from pathlib import Path

ALLOWED_ACTIONS = {"terminate", "kill", "renice"}


def respond(payload: dict, code: int = 0) -> None:
    print(json.dumps(payload, ensure_ascii=True))
    raise SystemExit(code)


def load_request() -> dict:
    raw = sys.stdin.read()
    try:
        payload = json.loads(raw or "{}")
    except json.JSONDecodeError:
        respond({"ok": False, "error": "invalid JSON request"}, 2)
    if not isinstance(payload, dict):
        respond({"ok": False, "error": "request must be a JSON object"}, 2)
    return payload


def proc_uid(pid: int) -> int:
    status = Path("/proc") / str(pid) / "status"
    with status.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.startswith("Uid:"):
                return int(line.split()[1])
    raise RuntimeError("could not read process owner")


def validate_pid(value) -> int:
    try:
        pid = int(value)
    except Exception as exc:
        raise RuntimeError("invalid PID") from exc
    if pid <= 1:
        raise RuntimeError("refusing to control PID 1 or lower")
    if pid == os.getpid() or pid == os.getppid():
        raise RuntimeError("refusing to control helper process")
    if not (Path("/proc") / str(pid)).exists():
        raise RuntimeError("process no longer exists")
    return pid


def validate_nice(value) -> int:
    try:
        nice = int(value)
    except Exception as exc:
        raise RuntimeError("invalid nice value") from exc
    if nice < -20 or nice > 19:
        raise RuntimeError("nice value must be between -20 and 19")
    return nice


def main() -> int:
    if os.geteuid() != 0:
        respond({"ok": False, "error": "helper must run as root"}, 3)
    req = load_request()
    action = str(req.get("action", "")).strip().lower()
    if action not in ALLOWED_ACTIONS:
        respond({"ok": False, "error": "unsupported action"}, 2)
    try:
        pid = validate_pid(req.get("pid"))
        _owner = proc_uid(pid)
        if action == "terminate":
            os.kill(pid, signal.SIGTERM)
            respond({"ok": True, "message": f"Sent terminate to PID {pid}"})
        if action == "kill":
            os.kill(pid, signal.SIGKILL)
            respond({"ok": True, "message": f"Sent kill to PID {pid}"})
        nice = validate_nice(req.get("value"))
        os.setpriority(os.PRIO_PROCESS, pid, nice)
        respond({"ok": True, "message": f"Set PID {pid} nice value to {nice}"})
    except Exception as exc:
        respond({"ok": False, "error": str(exc), "message": str(exc)}, 1)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
