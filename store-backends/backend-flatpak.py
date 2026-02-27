#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

FLATHUB_REPO_URL = "https://dl.flathub.org/repo/flathub.flatpakrepo"
CACHE_PATH = Path.home() / ".cache" / "crixa-store" / "flathub-index.json"
CACHE_TTL_SECONDS = 3600 * 12


def respond(payload: dict, code: int = 0) -> None:
    print(json.dumps(payload, ensure_ascii=True))
    raise SystemExit(code)


def run_cmd(args: list[str], timeout: int = 120) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, capture_output=True, text=True, check=False, timeout=timeout)


def ensure_flathub_remote() -> tuple[bool, str]:
    # User-level remote avoids requiring root in live desktop sessions.
    result = run_cmd(["flatpak", "remote-add", "--user", "--if-not-exists", "flathub", FLATHUB_REPO_URL], timeout=90)
    if result.returncode != 0:
        err = (result.stderr or result.stdout).strip()
        return False, err or "failed to add Flathub remote"
    check = run_cmd(["flatpak", "remotes", "--user", "--columns=name"], timeout=30)
    if check.returncode != 0:
        err = (check.stderr or check.stdout).strip()
        return False, err or "failed to query Flatpak remotes"
    names = {line.strip() for line in check.stdout.splitlines() if line.strip()}
    if "flathub" not in names:
        return False, "Flathub remote is unavailable"
    return True, "ok"


def split_columns(line: str) -> list[str]:
    if "\t" in line:
        return [part.strip() for part in line.split("\t")]
    return [part.strip() for part in line.split() if part.strip()]


def installed_map() -> dict[str, dict]:
    result = run_cmd(["flatpak", "list", "--user", "--app", "--columns=application,name,version,origin"], timeout=80)
    if result.returncode != 0:
        return {}
    out: dict[str, dict] = {}
    for raw in result.stdout.splitlines():
        cols = split_columns(raw)
        if not cols:
            continue
        app_id = cols[0]
        name = cols[1] if len(cols) > 1 else app_id
        version = cols[2] if len(cols) > 2 else ""
        origin = cols[3] if len(cols) > 3 else ""
        out[app_id] = {"id": app_id, "name": name, "version": version, "origin": origin}
    return out


def save_cache(rows: list[dict]) -> None:
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {"saved_at": int(time.time()), "apps": rows}
    CACHE_PATH.write_text(json.dumps(payload), encoding="utf-8")


def load_cache() -> list[dict]:
    try:
        payload = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return []
    saved_at = int(payload.get("saved_at", 0))
    if int(time.time()) - saved_at > CACHE_TTL_SECONDS:
        return []
    apps = payload.get("apps", [])
    if not isinstance(apps, list):
        return []
    return [row for row in apps if isinstance(row, dict)]


def refresh_index() -> tuple[list[dict], str]:
    result = run_cmd(
        ["flatpak", "remote-ls", "--user", "--app", "flathub", "--columns=application,name,version,description"],
        timeout=180,
    )
    if result.returncode != 0:
        err = (result.stderr or result.stdout).strip()
        return [], err or "failed to query Flathub index"
    rows: list[dict] = []
    for raw in result.stdout.splitlines():
        cols = split_columns(raw)
        if len(cols) < 1:
            continue
        app_id = cols[0]
        if "." not in app_id:
            continue
        name = cols[1] if len(cols) > 1 else app_id
        version = cols[2] if len(cols) > 2 else ""
        description = cols[3] if len(cols) > 3 else ""
        rows.append(
            {
                "id": app_id,
                "name": name,
                "version": version,
                "summary": description,
                "description": description,
                "category": "Flatpak",
                "source": "flathub",
            }
        )
    save_cache(rows)
    return rows, "ok"


def index_rows() -> tuple[list[dict], str]:
    cached = load_cache()
    if cached:
        return cached, "ok"
    return refresh_index()


def list_apps(query: str, limit: int) -> tuple[list[dict], str]:
    remote_ok, remote_msg = ensure_flathub_remote()
    installed = installed_map()

    if not query or not remote_ok:
        rows = []
        for app in installed.values():
            rows.append(
                {
                    "id": app["id"],
                    "name": app["name"] or app["id"],
                    "version": app["version"] or "installed",
                    "summary": f"Installed from {app.get('origin', 'flatpak')}",
                    "description": "Installed Flatpak app",
                    "category": "Flatpak",
                    "source": "flathub",
                    "installed": True,
                }
            )
        note = "Showing installed Flatpak apps. Type search text to discover Flathub apps."
        if not remote_ok:
            note = f"Flatpak remote issue: {remote_msg}"
        return sorted(rows, key=lambda row: row["name"].lower())[:limit], note

    rows = []
    query_l = query.lower()
    index, index_msg = index_rows()
    for item in index:
        app_id = str(item.get("id", ""))
        name = str(item.get("name", ""))
        summary = str(item.get("summary", ""))
        if query_l not in app_id.lower() and query_l not in name.lower() and query_l not in summary.lower():
            continue
        merged = dict(item)
        merged["installed"] = app_id in installed
        if merged["installed"] and installed[app_id].get("version"):
            merged["version"] = installed[app_id]["version"]
        rows.append(merged)
        if len(rows) >= limit:
            break
    return rows, index_msg


def install_app(app_id: str, force: bool) -> tuple[bool, str]:
    remote_ok, remote_msg = ensure_flathub_remote()
    if not remote_ok:
        return False, remote_msg
    if force:
        result = run_cmd(["flatpak", "update", "--user", "-y", app_id], timeout=900)
    else:
        result = run_cmd(["flatpak", "install", "--user", "-y", "flathub", app_id], timeout=900)
    if result.returncode != 0:
        return False, (result.stderr or result.stdout).strip() or "flatpak install failed"
    return True, (result.stdout or "installed").strip()


def remove_app(app_id: str) -> tuple[bool, str]:
    result = run_cmd(["flatpak", "uninstall", "--user", "-y", app_id], timeout=900)
    if result.returncode != 0:
        return False, (result.stderr or result.stdout).strip() or "flatpak remove failed"
    return True, (result.stdout or "removed").strip()


def launch_app(app_id: str) -> tuple[bool, str]:
    try:
        subprocess.Popen(["flatpak", "run", app_id], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception as exc:
        return False, str(exc)
    return True, "launched"


def upgrade_all() -> tuple[bool, str]:
    result = run_cmd(["flatpak", "update", "--user", "-y", "--app"], timeout=1800)
    if result.returncode != 0:
        return False, (result.stderr or result.stdout).strip() or "flatpak update failed"
    return True, (result.stdout or "updated").strip()


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


def main() -> int:
    if run_cmd(["flatpak", "--version"]).returncode != 0:
        respond({"ok": False, "error": "flatpak is not installed"}, 1)

    req = load_request()
    action = str(req.get("action", "")).strip().lower()
    query = str(req.get("query", "")).strip()
    app_id = str(req.get("app_id", "")).strip()
    force = bool(req.get("force", False))
    limit = int(req.get("limit", 240))
    limit = max(1, min(limit, 500))

    if action in ("list", "search"):
        apps, note = list_apps(query=query, limit=limit)
        respond({"ok": True, "apps": apps, "message": note})
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
