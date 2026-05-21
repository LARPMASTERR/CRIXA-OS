#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

BACKEND_ID = "crixa-repo"
BACKEND_NAME = "CRIXA Main"
CATALOG_PATH = Path("/usr/share/crixa-store/catalog.json")
REPO_ROOT = Path("/usr/share/crixa-repo")
LOCAL_PREFIX = Path.home() / ".local"

CONFIG_DIR = Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config"))) / "crixa-store"
SOURCES_PATH = CONFIG_DIR / "sources.json"
CACHE_ROOT = Path(os.environ.get("XDG_CACHE_HOME", str(Path.home() / ".cache"))) / "crixa-store" / "repos"
OPERATIONS_DIR = Path(os.environ.get("XDG_STATE_HOME", str(Path.home() / ".local" / "state"))) / "crixa-store" / "operations"

DEV_ROOT = Path(__file__).resolve().parents[1] if Path(__file__).resolve().parent.name == "store-backends" else None
DEV_CATALOG_PATH = DEV_ROOT / "store-packages" / "catalog.json" if DEV_ROOT else None
DEV_REPO_ROOT = DEV_ROOT / "crixa-repo" if DEV_ROOT else None
DEV_HELPER_PATH = DEV_ROOT / "store-backends" / "crixa-store-system-helper.py" if DEV_ROOT else None

PACKAGE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,80}$")
SOURCE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,80}$")
REMOTE_SCHEMES = {"http", "https"}


def respond(payload: dict, code: int = 0) -> None:
    if "ok" not in payload:
        payload["ok"] = code == 0
    if "message" not in payload and payload.get("error"):
        payload["message"] = str(payload["error"])
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


def load_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def save_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def run_cmd(args: list[str], timeout: int = 90, input_text: str | None = None) -> subprocess.CompletedProcess[str]:
    command = list(args)
    if command and command[0] == "crixapkg" and shutil.which("crixapkg") is None and DEV_ROOT is not None:
        local_pkg = DEV_ROOT / "apps" / "crixapkg.py"
        if local_pkg.exists():
            command = [sys.executable, str(local_pkg), *command[1:]]
    try:
        return subprocess.run(command, input=input_text, capture_output=True, text=True, check=False, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        return subprocess.CompletedProcess(command, 124, exc.stdout or "", exc.stderr or "command timed out")
    except FileNotFoundError as exc:
        return subprocess.CompletedProcess(command, 127, "", str(exc))


def operation_id(action: str) -> str:
    return f"{action}-{int(time.time())}-{uuid.uuid4().hex[:8]}"


def record_operation(op_id: str, payload: dict) -> None:
    try:
        OPERATIONS_DIR.mkdir(parents=True, exist_ok=True)
        save_json(OPERATIONS_DIR / f"{op_id}.json", payload)
    except Exception:
        pass


def source_cache_path(source_id: str) -> Path:
    return CACHE_ROOT / source_id


def safe_source_id(value: str) -> str:
    raw = re.sub(r"[^A-Za-z0-9._-]+", "-", value.strip().lower()).strip("-._")
    if not raw:
        raw = "source"
    raw = raw[:44]
    if not SOURCE_ID_RE.match(raw):
        raw = "source"
    return raw


def source_id_for_url(url: str, preferred: str = "") -> str:
    base = safe_source_id(preferred or urllib.parse.urlparse(url).netloc or Path(url).name or "repo")
    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:8]
    return f"{base}-{digest}"


def builtin_source() -> dict:
    repo_root = REPO_ROOT
    if DEV_REPO_ROOT is not None and (DEV_REPO_ROOT / "metadata" / "repo.json").exists():
        repo_root = DEV_REPO_ROOT
    return {
        "id": BACKEND_ID,
        "name": BACKEND_NAME,
        "url": str(repo_root),
        "enabled": True,
        "builtin": True,
        "signed": (repo_root / "metadata" / "repo.sig").exists(),
        "cache_path": str(repo_root),
        "repo_root": str(repo_root),
        "status": "ready" if (repo_root / "metadata" / "repo.json").exists() else "catalog-fallback",
    }


def load_config_sources() -> list[dict]:
    data = load_json(SOURCES_PATH, {"sources": []})
    rows = data.get("sources", []) if isinstance(data, dict) else []
    out: list[dict] = []
    if isinstance(rows, list):
        for row in rows:
            if not isinstance(row, dict):
                continue
            source_id = str(row.get("id", "")).strip()
            if not SOURCE_ID_RE.match(source_id):
                continue
            out.append(
                {
                    "id": source_id,
                    "name": str(row.get("name", source_id)).strip() or source_id,
                    "url": str(row.get("url", "")).strip(),
                    "enabled": bool(row.get("enabled", True)),
                    "builtin": False,
                    "signed": bool(row.get("signed", False)),
                    "cache_path": str(source_cache_path(source_id)),
                    "repo_root": str(source_cache_path(source_id)),
                    "status": str(row.get("status", "configured")),
                }
            )
    return out


def save_config_sources(sources: list[dict]) -> None:
    cleaned = []
    for row in sources:
        if row.get("builtin"):
            continue
        cleaned.append(
            {
                "id": row["id"],
                "name": row.get("name", row["id"]),
                "url": row.get("url", ""),
                "enabled": bool(row.get("enabled", True)),
                "signed": bool(row.get("signed", False)),
                "status": row.get("status", "configured"),
            }
        )
    save_json(SOURCES_PATH, {"sources": cleaned})


def all_sources() -> list[dict]:
    return [builtin_source(), *load_config_sources()]


def find_source(source_id: str) -> dict | None:
    for source in all_sources():
        if source.get("id") == source_id:
            return source
    return None


def local_file_from_url(url: str) -> Path | None:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme == "file":
        return Path(urllib.request.url2pathname(parsed.path))
    if not parsed.scheme:
        return Path(url).expanduser()
    return None


def fetch_bytes(url: str, timeout: int = 25) -> bytes:
    with urllib.request.urlopen(url, timeout=timeout) as response:
        return response.read()


def copy_or_download_file(base_url: str, relative: str, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    local_root = local_file_from_url(base_url)
    if local_root is not None:
        src = local_root / relative
        if not src.exists():
            raise RuntimeError(f"missing repository file: {src}")
        shutil.copy2(src, target)
        return
    parsed = urllib.parse.urlparse(base_url)
    if parsed.scheme not in REMOTE_SCHEMES:
        raise RuntimeError(f"unsupported repository URL scheme: {parsed.scheme or 'local'}")
    url = urllib.parse.urljoin(base_url.rstrip("/") + "/", relative)
    target.write_bytes(fetch_bytes(url))


def verify_repo_signature(repo_root: Path) -> tuple[bool, str]:
    metadata = repo_root / "metadata" / "repo.json"
    signature = repo_root / "metadata" / "repo.sig"
    public_key = repo_root / "keys" / "repo-public.pem"
    for required in (metadata, signature, public_key):
        if not required.exists():
            return False, f"missing signed repository file: {required.name}"
    result = subprocess.run(
        [
            "openssl",
            "dgst",
            "-sha256",
            "-verify",
            str(public_key),
            "-signature",
            str(signature),
            str(metadata),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return False, (result.stderr or result.stdout).strip() or "signature verification failed"
    return True, "ok"


def safe_relative_asset(value: str, app_id: str) -> str | None:
    raw = value.strip()
    if not raw:
        return None
    path = Path(raw)
    if path.is_absolute() or ".." in path.parts:
        return None
    if len(path.parts) == 1:
        return f"assets/{app_id}/{path.name}"
    return str(path)


def cache_declared_assets(source: dict, cache_path: Path) -> None:
    repo = load_json(cache_path / "metadata" / "repo.json", {"packages": []})
    packages = repo.get("packages", []) if isinstance(repo, dict) else []
    if not isinstance(packages, list):
        return
    base_url = str(source.get("url", ""))
    for item in packages:
        if not isinstance(item, dict):
            continue
        app_id = str(item.get("id", "")).strip()
        if not app_id:
            continue
        values = []
        if item.get("hero_image"):
            values.append(str(item.get("hero_image")))
        if isinstance(item.get("screenshots"), list):
            values.extend(str(value) for value in item["screenshots"])
        for value in values:
            rel = safe_relative_asset(value, app_id)
            if not rel:
                continue
            target = cache_path / rel
            if target.exists():
                continue
            try:
                copy_or_download_file(base_url, rel, target)
            except Exception:
                continue


def refresh_source(source: dict) -> dict:
    if source.get("builtin"):
        repo_root = Path(str(source.get("repo_root") or source.get("cache_path") or REPO_ROOT))
        if (repo_root / "metadata" / "repo.json").exists():
            ok, reason = verify_repo_signature(repo_root)
            if not ok:
                raise RuntimeError(reason)
            return {**source, "status": "ready", "signed": True}
        return {**source, "status": "catalog-fallback", "signed": False}

    source_id = str(source["id"])
    url = str(source.get("url", "")).strip()
    if not url:
        raise RuntimeError("source URL is required")
    cache_path = source_cache_path(source_id)
    copy_or_download_file(url, "metadata/repo.json", cache_path / "metadata" / "repo.json")
    copy_or_download_file(url, "metadata/repo.sig", cache_path / "metadata" / "repo.sig")
    copy_or_download_file(url, "keys/repo-public.pem", cache_path / "keys" / "repo-public.pem")
    ok, reason = verify_repo_signature(cache_path)
    if not ok:
        shutil.rmtree(cache_path, ignore_errors=True)
        raise RuntimeError(f"repository signature invalid: {reason}")
    cache_declared_assets(source, cache_path)
    refreshed = {**source, "signed": True, "status": "ready", "cache_path": str(cache_path), "repo_root": str(cache_path)}
    sources = [refreshed if row.get("id") == source_id else row for row in load_config_sources()]
    save_config_sources(sources)
    return refreshed


def load_repo_index(source: dict) -> tuple[dict, Path | None]:
    repo_root = Path(str(source.get("repo_root") or source.get("cache_path") or ""))
    repo_json = repo_root / "metadata" / "repo.json"
    if repo_json.exists():
        ok, reason = verify_repo_signature(repo_root)
        if not ok:
            raise RuntimeError(f"{source.get('name', source.get('id'))}: {reason}")
        data = load_json(repo_json, {"packages": []})
        if not isinstance(data, dict) or not isinstance(data.get("packages", []), list):
            raise RuntimeError(f"{source.get('name', source.get('id'))}: invalid repo metadata")
        return data, repo_root

    if source.get("builtin"):
        catalog_path = CATALOG_PATH
        if not catalog_path.exists() and DEV_CATALOG_PATH is not None and DEV_CATALOG_PATH.exists():
            catalog_path = DEV_CATALOG_PATH
        data = load_json(catalog_path, {"apps": []})
        apps = data.get("apps", []) if isinstance(data, dict) else []
        if not isinstance(apps, list):
            apps = []
        return {"repo": BACKEND_NAME, "format": 1, "packages": apps}, None
    raise RuntimeError(f"{source.get('name', source.get('id'))}: source has not been refreshed")


def installed_map(scope: str) -> dict[str, dict]:
    result = run_cmd(["crixapkg", "installed", "--json", "--scope", scope])
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
            if app_id:
                out[app_id] = item
    return out


def normalize_list(value) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item).strip()]


def normalize_release_notes(value) -> list[str]:
    if isinstance(value, str):
        return [value] if value.strip() else []
    return normalize_list(value)


def catalog_apps_by_id() -> dict[str, dict]:
    catalog_path = CATALOG_PATH
    if not catalog_path.exists() and DEV_CATALOG_PATH is not None and DEV_CATALOG_PATH.exists():
        catalog_path = DEV_CATALOG_PATH
    data = load_json(catalog_path, {"apps": []})
    apps = data.get("apps", []) if isinstance(data, dict) else []
    out: dict[str, dict] = {}
    if isinstance(apps, list):
        for row in apps:
            if isinstance(row, dict) and row.get("id"):
                out[str(row["id"])] = row
    return out


def shape_app(item: dict, source: dict, installed_user: dict, installed_system: dict) -> dict:
    app_id = str(item.get("id", "")).strip()
    catalog_item = catalog_apps_by_id().get(app_id, {})

    def field(key: str, default=None):
        value = item.get(key)
        if value in (None, "", []):
            value = catalog_item.get(key, default)
        return default if value is None else value

    source_id = str(source.get("id", BACKEND_ID))
    name = str(field("name", app_id or "Unnamed")).strip() or app_id or "Unnamed"
    install_scopes = normalize_list(field("install_scopes", []) or item.get("scopes"))
    if not install_scopes:
        install_scopes = ["user", "system"]
    installed_scopes = []
    if app_id in installed_user:
        installed_scopes.append("user")
    if app_id in installed_system:
        installed_scopes.append("system")
    return {
        "id": app_id,
        "name": name,
        "version": str(field("version", "n/a")),
        "category": str(field("category", "General")),
        "summary": str(field("summary", "")),
        "description": str(field("description", "")),
        "features": normalize_list(field("features", [])),
        "tags": normalize_list(field("tags", [])),
        "entrypoint": str(field("entrypoint", "")),
        "size": str(field("size", "") or item.get("size_hint") or ""),
        "installed": bool(installed_scopes),
        "installed_scopes": installed_scopes,
        "source": source_id,
        "source_id": source_id,
        "source_name": str(source.get("name", source_id)),
        "backend": BACKEND_ID,
        "publisher": str(field("publisher", "CRIXA Project")),
        "license": str(field("license", "MIT")),
        "homepage": str(field("homepage", "")),
        "release_notes": normalize_release_notes(field("release_notes", [])),
        "permissions": normalize_list(field("permissions", [])),
        "screenshots": normalize_list(field("screenshots", [])),
        "hero_image": str(field("hero_image", "")),
        "install_scopes": install_scopes,
        "asset_base": str(Path(str(source.get("repo_root") or source.get("cache_path") or "")) / "assets" / app_id),
    }


def list_apps(query: str, limit: int, source_id: str = "all") -> list[dict]:
    installed_user = installed_map("user")
    installed_system = installed_map("system")
    selected_sources = all_sources() if source_id in ("", "all", "*") else [find_source(source_id)]
    apps: list[dict] = []
    seen: set[tuple[str, str]] = set()
    query = query.lower().strip()
    for source in selected_sources:
        if not source or not source.get("enabled", True):
            continue
        try:
            repo, _repo_root = load_repo_index(source)
        except Exception as exc:
            apps.append(
                {
                    "id": f"source-error-{source.get('id')}",
                    "name": str(source.get("name", "Source error")),
                    "version": "",
                    "category": "Source",
                    "summary": str(exc),
                    "description": str(exc),
                    "features": [],
                    "tags": ["source-error"],
                    "entrypoint": "",
                    "size": "",
                    "installed": False,
                    "installed_scopes": [],
                    "source": str(source.get("id", "")),
                    "source_id": str(source.get("id", "")),
                    "source_name": str(source.get("name", "")),
                    "backend": BACKEND_ID,
                    "publisher": BACKEND_NAME,
                    "license": "",
                    "homepage": "",
                    "release_notes": [],
                    "permissions": [],
                    "screenshots": [],
                    "hero_image": "",
                    "install_scopes": [],
                    "asset_base": "",
                    "error": str(exc),
                }
            )
            continue
        packages = repo.get("packages", [])
        for item in packages:
            if not isinstance(item, dict):
                continue
            app = shape_app(item, source, installed_user, installed_system)
            app_id = app["id"]
            if not app_id:
                continue
            key = (app["source_id"], app_id)
            if key in seen:
                continue
            seen.add(key)
            haystack = " ".join(
                [
                    app_id,
                    app["name"],
                    app["summary"],
                    app["description"],
                    " ".join(app["features"]),
                    " ".join(app["tags"]),
                    app["publisher"],
                ]
            ).lower()
            if query and query not in haystack:
                continue
            apps.append(app)
            if len(apps) >= limit:
                return sorted(apps, key=lambda row: str(row.get("name", "")).lower())
    return sorted(apps, key=lambda row: str(row.get("name", "")).lower())


def package_entry(source: dict, app_id: str) -> dict | None:
    repo, _repo_root = load_repo_index(source)
    best = None
    for item in repo.get("packages", []):
        if isinstance(item, dict) and str(item.get("id", "")) == app_id:
            best = item
    return best


def ensure_package_cached(source: dict, app_id: str) -> Path:
    repo, repo_root = load_repo_index(source)
    if repo_root is None:
        raise RuntimeError("signed package repository is not available")
    app = package_entry(source, app_id)
    if not app:
        raise RuntimeError(f"package not found: {app_id}")
    filename = str(app.get("filename", "")).strip()
    if not filename:
        raise RuntimeError(f"package entry missing filename: {app_id}")
    package_path = repo_root / "packages" / filename
    if package_path.exists():
        return repo_root
    if source.get("builtin"):
        raise RuntimeError(f"package archive missing: {package_path}")
    copy_or_download_file(str(source.get("url", "")), f"packages/{filename}", package_path)
    expected = str(app.get("sha256", "")).strip().lower()
    if expected:
        digest = hashlib.sha256(package_path.read_bytes()).hexdigest().lower()
        if digest != expected:
            package_path.unlink(missing_ok=True)
            raise RuntimeError(f"package hash mismatch: {app_id}")
    return repo_root


def crixapkg_json(args: list[str], op_id: str, timeout: int = 180) -> tuple[bool, str, list[str]]:
    result = run_cmd(args, timeout=timeout)
    text = (result.stdout or "").strip()
    err = (result.stderr or "").strip()
    log = [line for line in (text + "\n" + err).splitlines() if line.strip()]
    if result.returncode != 0:
        return False, err or text or "operation failed", log
    message = "ok"
    if text:
        try:
            payload = json.loads(text)
            message = payload.get("status") or payload.get("message") or payload.get("id") or "ok"
            if isinstance(message, list):
                message = ", ".join(str(item) for item in message)
        except json.JSONDecodeError:
            message = text.splitlines()[-1]
    record_operation(op_id, {"ok": True, "message": str(message), "log": log, "finished_at": time.time()})
    return True, str(message), log


def run_system_helper(action: str, app_id: str, source: dict, repo_root: Path | None, force: bool = False) -> tuple[bool, str, list[str]]:
    helper = Path("/usr/lib/crixa-store/crixa-store-system-helper.py")
    if not helper.exists() and DEV_HELPER_PATH is not None and DEV_HELPER_PATH.exists():
        helper = DEV_HELPER_PATH
    if not helper.exists():
        return False, "system install helper is not installed", []
    payload = {
        "action": action,
        "app_id": app_id,
        "source_id": source.get("id", BACKEND_ID),
        "repo_root": str(repo_root or source.get("repo_root") or ""),
        "force": force,
    }
    command = [str(helper)]
    if os.geteuid() != 0:
        pkexec = shutil.which("pkexec")
        if not pkexec:
            return False, "pkexec is required for system installs", []
        command = [pkexec, str(helper)]
    result = run_cmd(command, timeout=240, input_text=json.dumps(payload))
    text = (result.stdout or "").strip()
    err = (result.stderr or "").strip()
    log = [line for line in (text + "\n" + err).splitlines() if line.strip()]
    if result.returncode != 0:
        return False, err or text or "system operation failed", log
    try:
        response = json.loads(text or "{}")
    except json.JSONDecodeError:
        response = {"ok": True, "message": text or "ok"}
    return bool(response.get("ok", True)), str(response.get("message", "ok")), log


def install_app(app_id: str, source_id: str, scope: str, force: bool) -> dict:
    if not PACKAGE_ID_RE.match(app_id):
        raise RuntimeError("invalid package id")
    source = find_source(source_id) or builtin_source()
    op_id = operation_id("install")
    record_operation(op_id, {"ok": None, "action": "install", "app_id": app_id, "scope": scope, "started_at": time.time()})
    repo_root = ensure_package_cached(source, app_id)
    if scope == "system":
        ok, message, log = run_system_helper("install", app_id, source, repo_root, force=force)
    else:
        cmd = ["crixapkg", "install", app_id, "--json", "--scope", "user", "--repo-root", str(repo_root)]
        if force:
            cmd.append("--force")
        ok, message, log = crixapkg_json(cmd, op_id)
    payload = {"ok": ok, "message": message, "operation_id": op_id, "progress": 100 if ok else 0, "log": log}
    record_operation(op_id, payload)
    return payload


def remove_app(app_id: str, scope: str) -> dict:
    if not PACKAGE_ID_RE.match(app_id):
        raise RuntimeError("invalid package id")
    op_id = operation_id("remove")
    record_operation(op_id, {"ok": None, "action": "remove", "app_id": app_id, "scope": scope, "started_at": time.time()})
    if scope == "system":
        ok, message, log = run_system_helper("remove", app_id, builtin_source(), None)
    else:
        ok, message, log = crixapkg_json(["crixapkg", "remove", app_id, "--json", "--scope", "user"], op_id)
    payload = {"ok": ok, "message": message, "operation_id": op_id, "progress": 100 if ok else 0, "log": log}
    record_operation(op_id, payload)
    return payload


def launch_app(app_id: str, source_id: str) -> tuple[bool, str]:
    source = find_source(source_id) or builtin_source()
    app = package_entry(source, app_id)
    if app is None:
        return False, "app not found"
    entrypoint = str(app.get("entrypoint", "")).strip()
    if not entrypoint:
        return False, "entrypoint missing"
    env = os.environ.copy()
    env["PATH"] = f"{LOCAL_PREFIX / 'bin'}:/usr/local/bin:{env.get('PATH', '')}"
    try:
        subprocess.Popen([entrypoint], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception as exc:
        return False, str(exc)
    return True, "launched"


def upgrade_all(source_id: str, scope: str) -> dict:
    source = find_source(source_id) or builtin_source()
    repo, repo_root = load_repo_index(source)
    if repo_root is None:
        raise RuntimeError("signed package repository is not available")
    for item in repo.get("packages", []):
        if isinstance(item, dict) and item.get("filename"):
            ensure_package_cached(source, str(item.get("id", "")))
    op_id = operation_id("upgrade")
    if scope == "system":
        ok, message, log = run_system_helper("upgrade", "", source, repo_root)
    else:
        ok, message, log = crixapkg_json(["crixapkg", "upgrade", "--json", "--scope", "user", "--repo-root", str(repo_root)], op_id, timeout=240)
    payload = {"ok": ok, "message": message, "operation_id": op_id, "progress": 100 if ok else 0, "log": log}
    record_operation(op_id, payload)
    return payload


def add_source(req: dict) -> dict:
    url = str(req.get("url", "")).strip()
    if not url:
        raise RuntimeError("source URL is required")
    source_id = str(req.get("source_id", "")).strip() or source_id_for_url(url, str(req.get("name", "")))
    if not SOURCE_ID_RE.match(source_id) or source_id == BACKEND_ID:
        raise RuntimeError("invalid source id")
    sources = load_config_sources()
    if any(row.get("id") == source_id for row in sources):
        raise RuntimeError(f"source already exists: {source_id}")
    source = {
        "id": source_id,
        "name": str(req.get("name", source_id)).strip() or source_id,
        "url": url,
        "enabled": True,
        "builtin": False,
        "signed": False,
        "status": "configured",
        "cache_path": str(source_cache_path(source_id)),
        "repo_root": str(source_cache_path(source_id)),
    }
    sources.append(source)
    save_config_sources(sources)
    try:
        refreshed = refresh_source(source)
    except Exception:
        save_config_sources([row for row in load_config_sources() if row.get("id") != source_id])
        shutil.rmtree(source_cache_path(source_id), ignore_errors=True)
        raise
    return {"ok": True, "message": f"Added {refreshed['name']}", "sources": all_sources()}


def remove_source(source_id: str) -> dict:
    if source_id == BACKEND_ID:
        raise RuntimeError("the built-in CRIXA source cannot be removed")
    sources = load_config_sources()
    kept = [row for row in sources if row.get("id") != source_id]
    if len(kept) == len(sources):
        raise RuntimeError(f"source not found: {source_id}")
    save_config_sources(kept)
    shutil.rmtree(source_cache_path(source_id), ignore_errors=True)
    return {"ok": True, "message": f"Removed {source_id}", "sources": all_sources()}


def capabilities() -> dict:
    helper = Path("/usr/lib/crixa-store/crixa-store-system-helper.py")
    if not helper.exists() and DEV_HELPER_PATH is not None:
        helper = DEV_HELPER_PATH
    return {
        "ok": True,
        "message": "ready",
        "capabilities": [
            "capabilities",
            "sources",
            "add-source",
            "remove-source",
            "refresh-source",
            "list",
            "install",
            "remove",
            "launch",
            "upgrade",
        ],
        "scopes": ["user", "system"],
        "requires_signed_metadata": True,
        "paths": {
            "sources": str(SOURCES_PATH),
            "cache": str(CACHE_ROOT),
            "operations": str(OPERATIONS_DIR),
            "system_helper": str(helper),
        },
        "system_helper_available": helper.exists() and (os.geteuid() == 0 or shutil.which("pkexec") is not None),
    }


def main() -> int:
    req = load_request()
    action = str(req.get("action", "")).strip().lower()
    query = str(req.get("query", "")).strip()
    app_id = str(req.get("app_id", "")).strip()
    raw_source = req.get("source_id") or req.get("source")
    source_id = str(raw_source or "").strip()
    scope = "system" if str(req.get("scope", "user")).lower() == "system" else "user"
    force = bool(req.get("force", False))
    try:
        limit = int(req.get("limit", 240))
    except Exception:
        limit = 240
    limit = max(1, min(limit, 800))

    try:
        if action == "capabilities":
            respond(capabilities())
        if action == "sources":
            respond({"ok": True, "message": "ok", "sources": all_sources()})
        if action == "add-source":
            respond(add_source(req))
        if action == "remove-source":
            respond(remove_source(source_id))
        if action == "refresh-source":
            if source_id in ("", "all", "*"):
                refreshed = [refresh_source(row) for row in all_sources()]
            else:
                source = find_source(source_id)
                if not source:
                    raise RuntimeError(f"source not found: {source_id}")
                refreshed = [refresh_source(source)]
            respond({"ok": True, "message": "refreshed", "sources": refreshed})
        if action in ("list", "search"):
            respond({"ok": True, "apps": list_apps(query=query, limit=limit, source_id=source_id or "all"), "sources": all_sources(), "message": "ok"})
        if action == "install":
            respond(install_app(app_id=app_id, source_id=source_id or BACKEND_ID, scope=scope, force=force), 0)
        if action == "remove":
            respond(remove_app(app_id=app_id, scope=scope), 0)
        if action == "launch":
            ok, msg = launch_app(app_id=app_id, source_id=source_id or BACKEND_ID)
            respond({"ok": ok, "message": msg}, 0 if ok else 1)
        if action == "upgrade":
            respond(upgrade_all(source_id=source_id or BACKEND_ID, scope=scope), 0)
    except Exception as exc:
        respond({"ok": False, "error": str(exc), "message": str(exc), "progress": 0}, 1)

    respond({"ok": False, "error": f"unsupported action: {action}"}, 2)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
