#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

CATALOG_PATH = Path("/usr/share/crixa-store/catalog.json")
LOCAL_PREFIX = Path.home() / ".local"


def respond(payload: dict, code: int = 0) -> None:
    print(json.dumps(payload, ensure_ascii=True))
    raise SystemExit(code)


def load_request() -> dict:
    raw = sys.stdin.read()
    if not raw.strip():
        return {}
    try:
        req = json.loads(raw)
    except json.JSONDecodeError:
        respond({"ok": False, "error": "invalid JSON request"}, 2)
    if not isinstance(req, dict):
        respond({"ok": False, "error": "request must be JSON object"}, 2)
    return req


def run_cmd(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, capture_output=True, text=True, check=False)


def load_catalog() -> list[dict]:
    try:
        data = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    except Exception:
        return []
    apps = data.get("apps", [])
    if not isinstance(apps, list):
        return []
    out = []
    for item in apps:
        if isinstance(item, dict) and item.get("id") and item.get("name"):
            out.append(item)
    return sorted(out, key=lambda row: str(row.get("name", "")).lower())


def installed_map() -> dict[str, dict]:
    result = run_cmd(["crixapkg", "installed", "--json"])
    if result.returncode != 0:
        return {}
    try:
        payload = json.loads(result.stdout or "{}")
    except json.JSONDecodeError:
        return {}
    apps = payload.get("apps", [])
    out: dict[str, dict] = {}
    if isinstance(apps, list):
        for item in apps:
            if not isinstance(item, dict):
                continue
            app_id = str(item.get("id", "")).strip()
            if not app_id:
                continue
            out[app_id] = item
    return out


def list_apps(query: str, limit: int) -> list[dict]:
    installed = installed_map()
    apps = []
    for item in load_catalog():
        app_id = str(item.get("id", ""))
        haystack = " ".join(
            [
                str(item.get("name", "")),
                str(item.get("summary", "")),
                str(item.get("description", "")),
                " ".join(item.get("features", [])) if isinstance(item.get("features"), list) else "",
            ]
        ).lower()
        if query and query not in haystack and query not in app_id.lower():
            continue
        app = {
            "id": app_id,
            "name": str(item.get("name", app_id)),
            "version": str(item.get("version", "n/a")),
            "category": str(item.get("category", "CRIXA")),
            "summary": str(item.get("summary", "")),
            "description": str(item.get("description", "")),
            "features": item.get("features", []) if isinstance(item.get("features"), list) else [],
            "entrypoint": str(item.get("entrypoint", "")),
            "size": str(item.get("size", "")),
            "installed": app_id in installed,
            "source": "crixa-repo",
        }
        apps.append(app)
        if len(apps) >= limit:
            break
    return apps


def install_app(app_id: str, force: bool) -> tuple[bool, str]:
    cmd = ["crixapkg", "install", app_id]
    if force:
        cmd.append("--force")
    result = run_cmd(cmd)
    if result.returncode != 0:
        return False, (result.stderr or result.stdout).strip() or "install failed"
    return True, (result.stdout or "installed").strip()


def remove_app(app_id: str) -> tuple[bool, str]:
    result = run_cmd(["crixapkg", "remove", app_id])
    if result.returncode != 0:
        return False, (result.stderr or result.stdout).strip() or "remove failed"
    return True, (result.stdout or "removed").strip()


def launch_app(app_id: str) -> tuple[bool, str]:
    app = None
    for row in load_catalog():
        if str(row.get("id", "")) == app_id:
            app = row
            break
    if app is None:
        return False, "app not found"
    entrypoint = str(app.get("entrypoint", "")).strip()
    if not entrypoint:
        return False, "entrypoint missing"
    env = os.environ.copy()
    env["PATH"] = f"{LOCAL_PREFIX / 'bin'}:{env.get('PATH', '')}"
    try:
        subprocess.Popen([entrypoint], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception as exc:
        return False, str(exc)
    return True, "launched"


def upgrade_all() -> tuple[bool, str]:
    result = run_cmd(["crixapkg", "upgrade"])
    if result.returncode != 0:
        return False, (result.stderr or result.stdout).strip() or "upgrade failed"
    return True, (result.stdout or "upgraded").strip()


def main() -> int:
    req = load_request()
    action = str(req.get("action", "")).strip().lower()
    query = str(req.get("query", "")).strip().lower()
    app_id = str(req.get("app_id", "")).strip()
    force = bool(req.get("force", False))
    limit = int(req.get("limit", 240))
    limit = max(1, min(limit, 500))

    if action in ("list", "search"):
        respond({"ok": True, "apps": list_apps(query=query, limit=limit), "message": "ok"})
    if action == "install":
        ok, msg = install_app(app_id=app_id, force=force)
        respond({"ok": ok, "message": msg}, 0 if ok else 1)
    if action == "remove":
        ok, msg = remove_app(app_id=app_id)
        respond({"ok": ok, "message": msg}, 0 if ok else 1)
    if action == "launch":
        ok, msg = launch_app(app_id=app_id)
        respond({"ok": ok, "message": msg}, 0 if ok else 1)
    if action == "upgrade":
        ok, msg = upgrade_all()
        respond({"ok": ok, "message": msg}, 0 if ok else 1)
    if action == "capabilities":
        respond(
            {
                "ok": True,
                "capabilities": ["list", "install", "remove", "launch", "upgrade"],
            }
        )
    respond({"ok": False, "error": f"unsupported action: {action}"}, 2)


if __name__ == "__main__":
    raise SystemExit(main())
