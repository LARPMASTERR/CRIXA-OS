#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

PACKAGE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,80}$")
SOURCE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,80}$")
ALLOWED_ACTIONS = {"install", "remove", "upgrade"}


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
        respond({"ok": False, "error": "request must be an object"}, 2)
    return payload


def repo_root_allowed(path: Path) -> bool:
    try:
        resolved = path.resolve()
    except Exception:
        return False
    allowed_prefixes = [
        Path("/usr/share/crixa-repo"),
        Path("/var/cache/crixa-store/repos"),
        Path("/tmp/crixa-store-repos"),
    ]
    for prefix in allowed_prefixes:
        try:
            if resolved == prefix.resolve() or resolved.is_relative_to(prefix.resolve()):
                return True
        except Exception:
            continue
    parts = resolved.parts
    return len(parts) >= 5 and parts[0] == "/" and parts[1] == "home" and parts[3] == ".cache" and parts[4] == "crixa-store"


def validate_repo_root(raw: str) -> Path:
    repo_root = Path(raw).expanduser()
    if not repo_root_allowed(repo_root):
        raise RuntimeError("repo root is outside allowed store locations")
    for rel in ("metadata/repo.json", "metadata/repo.sig", "keys/repo-public.pem"):
        if not (repo_root / rel).exists():
            raise RuntimeError(f"repo root missing {rel}")
    return repo_root


def crixapkg_command() -> list[str]:
    executable = shutil.which("crixapkg")
    if executable:
        return [executable]
    local = Path(__file__).resolve().parents[1] / "apps" / "crixapkg.py"
    if local.exists():
        return [sys.executable, str(local)]
    return ["crixapkg"]


def main() -> int:
    req = load_request()
    action = str(req.get("action", "")).strip().lower()
    app_id = str(req.get("app_id", "")).strip()
    source_id = str(req.get("source_id", "")).strip()
    force = bool(req.get("force", False))

    if os.geteuid() != 0:
        respond({"ok": False, "error": "system helper must run as root"}, 3)
    if action not in ALLOWED_ACTIONS:
        respond({"ok": False, "error": "unsupported privileged action"}, 2)
    if source_id and not SOURCE_ID_RE.match(source_id):
        respond({"ok": False, "error": "invalid source id"}, 2)
    if action != "upgrade" and not PACKAGE_ID_RE.match(app_id):
        respond({"ok": False, "error": "invalid package id"}, 2)

    try:
        repo_root = validate_repo_root(str(req.get("repo_root", ""))) if action in {"install", "upgrade"} else None
    except Exception as exc:
        respond({"ok": False, "error": str(exc)}, 2)

    command = crixapkg_command()
    if action == "install":
        command += ["install", app_id, "--json", "--scope", "system", "--repo-root", str(repo_root)]
        if force:
            command.append("--force")
    elif action == "remove":
        command += ["remove", app_id, "--json", "--scope", "system"]
    else:
        command += ["upgrade", "--json", "--scope", "system", "--repo-root", str(repo_root)]

    result = subprocess.run(command, capture_output=True, text=True, check=False, timeout=240)
    stdout = (result.stdout or "").strip()
    stderr = (result.stderr or "").strip()
    if result.returncode != 0:
        respond({"ok": False, "error": stderr or stdout or "system package operation failed", "log": [stdout, stderr]}, 1)
    message = "ok"
    if stdout:
        try:
            payload = json.loads(stdout)
            message = str(payload.get("status") or payload.get("message") or payload.get("id") or "ok")
        except json.JSONDecodeError:
            message = stdout.splitlines()[-1]
    respond({"ok": True, "message": message, "log": [line for line in (stdout + "\n" + stderr).splitlines() if line.strip()]})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
