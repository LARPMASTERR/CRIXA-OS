#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_REPO_ROOT = Path("/usr/share/crixa-repo")
REPO_ROOT = DEFAULT_REPO_ROOT
REPO_METADATA = REPO_ROOT / "metadata" / "repo.json"
REPO_SIGNATURE = REPO_ROOT / "metadata" / "repo.sig"
REPO_PUBLIC_KEY = REPO_ROOT / "keys" / "repo-public.pem"

ACTIVE_SCOPE = "user"
LOCAL_PREFIX = Path.home() / ".local"
STATE_HOME = Path(os.environ.get("XDG_STATE_HOME", str(LOCAL_PREFIX / "state"))) / "crixapkg"
STATE_FILE = STATE_HOME / "installed.json"
SNAPSHOT_ROOT = STATE_HOME / "snapshots"
MAX_SNAPSHOTS = 16

TARGET_MAP = {
    "bin": LOCAL_PREFIX / "bin",
    "applications": LOCAL_PREFIX / "share" / "applications",
    "icons": LOCAL_PREFIX / "share" / "icons",
    "lib": LOCAL_PREFIX / "lib",
    "share": LOCAL_PREFIX / "share",
}

SYSTEM_PREFIX = Path("/usr/local")
SYSTEM_STATE_HOME = Path("/var/lib/crixapkg")


def configure_repo(repo_root: str | None) -> None:
    global REPO_ROOT, REPO_METADATA, REPO_SIGNATURE, REPO_PUBLIC_KEY
    root = Path(repo_root).expanduser() if repo_root else DEFAULT_REPO_ROOT
    REPO_ROOT = root
    REPO_METADATA = REPO_ROOT / "metadata" / "repo.json"
    REPO_SIGNATURE = REPO_ROOT / "metadata" / "repo.sig"
    REPO_PUBLIC_KEY = REPO_ROOT / "keys" / "repo-public.pem"


def configure_scope(scope: str) -> None:
    global ACTIVE_SCOPE, LOCAL_PREFIX, STATE_HOME, STATE_FILE, SNAPSHOT_ROOT, TARGET_MAP
    ACTIVE_SCOPE = "system" if scope == "system" else "user"
    if ACTIVE_SCOPE == "system":
        LOCAL_PREFIX = SYSTEM_PREFIX
        STATE_HOME = SYSTEM_STATE_HOME
    else:
        LOCAL_PREFIX = Path.home() / ".local"
        STATE_HOME = Path(os.environ.get("XDG_STATE_HOME", str(LOCAL_PREFIX / "state"))) / "crixapkg"
    TARGET_MAP = {
        "bin": LOCAL_PREFIX / "bin",
        "applications": LOCAL_PREFIX / "share" / "applications",
        "icons": LOCAL_PREFIX / "share" / "icons",
        "lib": LOCAL_PREFIX / "lib",
        "share": LOCAL_PREFIX / "share",
    }
    STATE_FILE = STATE_HOME / "installed.json"
    SNAPSHOT_ROOT = STATE_HOME / "snapshots"


def load_json(path: Path, default: dict) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def save_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def state() -> dict:
    data = load_json(STATE_FILE, {"apps": {}})
    if "apps" not in data or not isinstance(data["apps"], dict):
        data["apps"] = {}
    return data


def version_key(version: str) -> tuple:
    parts = re.findall(r"[0-9]+|[a-zA-Z]+", version)
    key = []
    for part in parts:
        if part.isdigit():
            key.append((0, int(part)))
        else:
            key.append((1, part.lower()))
    return tuple(key)


def sha256sum(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_repo_signature() -> tuple[bool, str]:
    for required in (REPO_METADATA, REPO_SIGNATURE, REPO_PUBLIC_KEY):
        if not required.exists():
            return False, f"missing repo file: {required}"

    cmd = [
        "openssl",
        "dgst",
        "-sha256",
        "-verify",
        str(REPO_PUBLIC_KEY),
        "-signature",
        str(REPO_SIGNATURE),
        str(REPO_METADATA),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        stderr = result.stderr.strip()
        stdout = result.stdout.strip()
        return False, stderr or stdout or "signature verification failed"
    return True, "ok"


def load_repo(require_signature: bool = True) -> dict:
    if require_signature:
        ok, reason = verify_repo_signature()
        if not ok:
            raise RuntimeError(f"repository signature invalid: {reason}")
    data = load_json(REPO_METADATA, {"packages": []})
    packages = data.get("packages", [])
    if not isinstance(packages, list):
        raise RuntimeError("repository index format error: 'packages' must be a list")
    return data


def package_index(repo: dict) -> dict[str, dict]:
    indexed: dict[str, dict] = {}
    for item in repo.get("packages", []):
        if not isinstance(item, dict):
            continue
        app_id = str(item.get("id", "")).strip()
        version = str(item.get("version", "")).strip()
        if not app_id or not version:
            continue
        previous = indexed.get(app_id)
        if previous is None or version_key(version) > version_key(str(previous.get("version", "0"))):
            indexed[app_id] = item
    return indexed


def ensure_within_scope(path: Path) -> bool:
    try:
        resolved = path.resolve()
        if ACTIVE_SCOPE == "system":
            roots = [
                (SYSTEM_PREFIX / "bin").resolve(),
                (SYSTEM_PREFIX / "lib").resolve(),
                (SYSTEM_PREFIX / "share").resolve(),
            ]
        else:
            roots = [LOCAL_PREFIX.resolve()]
        return any(resolved.is_relative_to(root) for root in roots)
    except Exception:
        return False


def refresh_caches() -> None:
    apps_dir = LOCAL_PREFIX / "share" / "applications"
    icon_dir = LOCAL_PREFIX / "share" / "icons" / "hicolor"
    if apps_dir.exists():
        subprocess.run(["update-desktop-database", str(apps_dir)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
    if icon_dir.exists():
        subprocess.run(["gtk-update-icon-cache", "-f", str(icon_dir)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
    if ACTIVE_SCOPE == "system":
        subprocess.run(["update-desktop-database", "/usr/local/share/applications"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
        subprocess.run(["gtk-update-icon-cache", "-f", "/usr/local/share/icons/hicolor"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)


def copy_payload(payload_root: Path) -> list[str]:
    installed: list[str] = []
    for section in payload_root.iterdir():
        if not section.is_dir():
            continue
        target_base = TARGET_MAP.get(section.name)
        if not target_base:
            continue
        target_base.mkdir(parents=True, exist_ok=True)
        for src in section.rglob("*"):
            rel = src.relative_to(section)
            dst = target_base / rel
            if src.is_dir():
                dst.mkdir(parents=True, exist_ok=True)
                continue
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            if section.name == "bin":
                dst.chmod(0o755)
            installed.append(str(dst))
    return installed


def cleanup_empty_parents(path: Path) -> None:
    try:
        root = LOCAL_PREFIX.resolve()
        current = path.parent.resolve()
    except Exception:
        return
    while current != root and current.exists():
        try:
            current.rmdir()
        except OSError:
            break
        current = current.parent


def managed_files_from_state(data: dict) -> list[Path]:
    files: list[Path] = []
    for app_state in data.get("apps", {}).values():
        if not isinstance(app_state, dict):
            continue
        entries = app_state.get("files", [])
        if not isinstance(entries, list):
            continue
        for item in entries:
            path = Path(str(item))
            if ensure_within_scope(path):
                files.append(path)
    # Remove duplicates while preserving relative order.
    seen: set[str] = set()
    unique: list[Path] = []
    for path in files:
        key = str(path)
        if key in seen:
            continue
        seen.add(key)
        unique.append(path)
    return unique


def remove_installed_files(files: list[Path]) -> None:
    # Delete deepest paths first to reduce directory cleanup churn.
    ordered = sorted(files, key=lambda path: len(str(path)), reverse=True)
    for path in ordered:
        if not ensure_within_scope(path):
            continue
        try:
            if path.exists():
                path.unlink()
        except Exception:
            pass
        cleanup_empty_parents(path)


def remove_app(app_id: str, data: dict) -> bool:
    record = data.get("apps", {}).get(app_id)
    if not record:
        return False
    files = record.get("files", [])
    if isinstance(files, list):
        remove_installed_files([Path(str(item)) for item in files])
    data["apps"].pop(app_id, None)
    save_json(STATE_FILE, data)
    refresh_caches()
    return True


def install_app(app_id: str, force: bool = False, no_verify: bool = False) -> dict:
    repo = load_repo(require_signature=not no_verify)
    idx = package_index(repo)
    item = idx.get(app_id)
    if item is None:
        raise RuntimeError(f"package not found in repo: {app_id}")

    app_version = str(item.get("version", "0"))
    pkg_file = str(item.get("filename", "")).strip()
    if not pkg_file:
        raise RuntimeError(f"package entry missing filename for {app_id}")

    package_path = REPO_ROOT / "packages" / pkg_file
    if not package_path.exists():
        raise RuntimeError(f"package archive missing: {package_path}")

    expected_hash = str(item.get("sha256", "")).strip().lower()
    actual_hash = sha256sum(package_path).lower()
    if expected_hash and expected_hash != actual_hash:
        raise RuntimeError(f"package hash mismatch for {app_id}")

    data = state()
    installed = data["apps"].get(app_id)
    if installed and str(installed.get("version", "")) == app_version and not force:
        return {"status": "unchanged", "id": app_id, "version": app_version}

    if installed:
        remove_app(app_id, data)
        data = state()

    with tempfile.TemporaryDirectory(prefix="crixapkg-install-") as tmpdir:
        tmp_path = Path(tmpdir)
        with tarfile.open(package_path, "r:gz") as archive:
            archive.extractall(tmp_path)
        manifest_path = tmp_path / "manifest.json"
        payload_root = tmp_path / "payload"
        if not manifest_path.exists() or not payload_root.is_dir():
            raise RuntimeError(f"package archive malformed: {pkg_file}")

        manifest = load_json(manifest_path, {})
        if str(manifest.get("id", "")) != app_id:
            raise RuntimeError(f"manifest id mismatch in {pkg_file}")
        if str(manifest.get("version", "")) != app_version:
            raise RuntimeError(f"manifest version mismatch in {pkg_file}")

        files = copy_payload(payload_root)
        if not files:
            raise RuntimeError(f"package contains no installable files: {pkg_file}")

    data["apps"][app_id] = {
        "name": item.get("name", app_id),
        "version": app_version,
        "entrypoint": item.get("entrypoint", ""),
        "installed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "files": files,
        "archive": pkg_file,
        "sha256": actual_hash,
        "scope": ACTIVE_SCOPE,
    }
    save_json(STATE_FILE, data)
    refresh_caches()
    return {"status": "installed", "id": app_id, "version": app_version}


def installed_as_list(data: dict) -> list[dict]:
    out = []
    for app_id, payload in sorted(data.get("apps", {}).items()):
        if not isinstance(payload, dict):
            continue
        out.append(
            {
                "id": app_id,
                "name": payload.get("name", app_id),
                "version": payload.get("version", ""),
                "entrypoint": payload.get("entrypoint", ""),
                "installed_at": payload.get("installed_at", ""),
                "files": payload.get("files", []),
                "scope": payload.get("scope", ACTIVE_SCOPE),
            }
        )
    return out


def snapshot_id() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    suffix = os.urandom(3).hex()
    return f"{stamp}-{suffix}"


def create_snapshot(reason: str, data: dict | None = None) -> str:
    current = data or state()
    snap_id = snapshot_id()
    snap_dir = SNAPSHOT_ROOT / snap_id
    files_dir = snap_dir / "files"
    files_dir.mkdir(parents=True, exist_ok=True)

    tracked = managed_files_from_state(current)
    scope_root = LOCAL_PREFIX.resolve()
    copied = 0
    for path in tracked:
        try:
            src = path.resolve()
        except Exception:
            continue
        if not src.exists():
            continue
        try:
            rel = src.relative_to(scope_root)
        except Exception:
            continue
        dst = files_dir / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        copied += 1

    save_json(snap_dir / "state.json", current)
    save_json(
        snap_dir / "meta.json",
        {
            "id": snap_id,
            "reason": reason,
            "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "tracked_files": len(tracked),
            "copied_files": copied,
        },
    )
    prune_snapshots(MAX_SNAPSHOTS)
    return snap_id


def restore_snapshot(snap_id: str) -> dict:
    snap_dir = SNAPSHOT_ROOT / snap_id
    files_dir = snap_dir / "files"
    state_file = snap_dir / "state.json"
    meta_file = snap_dir / "meta.json"

    if not snap_dir.is_dir():
        raise RuntimeError(f"snapshot not found: {snap_id}")
    if not state_file.exists():
        raise RuntimeError(f"snapshot state missing: {state_file}")

    target_state = load_json(state_file, {"apps": {}})
    current_state = state()

    # Remove all files currently managed by crixapkg before restoring snapshot files.
    remove_installed_files(managed_files_from_state(current_state))

    scope_root = LOCAL_PREFIX.resolve()
    restored = 0
    if files_dir.is_dir():
        for src in files_dir.rglob("*"):
            if src.is_dir():
                continue
            rel = src.relative_to(files_dir)
            if ACTIVE_SCOPE == "user" and rel.parts and rel.parts[0] == ".local":
                dst = Path.home() / rel
            else:
                dst = scope_root / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            restored += 1
            if str(dst).startswith(str(LOCAL_PREFIX / "bin")):
                try:
                    dst.chmod(0o755)
                except Exception:
                    pass

    save_json(STATE_FILE, target_state)
    refresh_caches()

    meta = load_json(meta_file, {})
    return {
        "id": snap_id,
        "reason": meta.get("reason", ""),
        "restored_files": restored,
    }


def list_snapshots() -> list[dict]:
    if not SNAPSHOT_ROOT.is_dir():
        return []
    rows: list[dict] = []
    for snap_dir in sorted(SNAPSHOT_ROOT.iterdir(), key=lambda path: path.name, reverse=True):
        if not snap_dir.is_dir():
            continue
        meta = load_json(snap_dir / "meta.json", {})
        rows.append(
            {
                "id": snap_dir.name,
                "created_at": meta.get("created_at", ""),
                "reason": meta.get("reason", ""),
                "tracked_files": meta.get("tracked_files", 0),
                "copied_files": meta.get("copied_files", 0),
            }
        )
    return rows


def prune_snapshots(max_keep: int) -> None:
    if not SNAPSHOT_ROOT.is_dir():
        return
    dirs = [path for path in SNAPSHOT_ROOT.iterdir() if path.is_dir()]
    dirs.sort(key=lambda path: path.name, reverse=True)
    for old in dirs[max_keep:]:
        shutil.rmtree(old, ignore_errors=True)


def with_transaction(reason: str, action) -> tuple[dict, str]:
    current = state()
    snap_id = create_snapshot(reason, current)
    try:
        result = action()
    except Exception as exc:
        restore_snapshot(snap_id)
        raise RuntimeError(f"{exc} (rolled back using snapshot {snap_id})") from exc
    return result, snap_id


def cmd_verify(args: argparse.Namespace) -> int:
    ok, reason = verify_repo_signature()
    if args.json:
        print(json.dumps({"ok": ok, "message": reason}, indent=2))
    else:
        print("ok" if ok else f"failed: {reason}")
    return 0 if ok else 2


def cmd_list(args: argparse.Namespace) -> int:
    try:
        repo = load_repo(require_signature=not args.no_verify)
    except Exception as exc:
        if args.json:
            print(json.dumps({"ok": False, "error": str(exc), "packages": []}, indent=2))
        else:
            print(f"list failed: {exc}", file=sys.stderr)
        return 1
    items = sorted(package_index(repo).values(), key=lambda item: str(item.get("name", "")).lower())
    if args.json:
        print(json.dumps({"packages": items}, indent=2))
        return 0
    for item in items:
        print(f"{item.get('id','?'):<20} {item.get('version','?'):<10} {item.get('name','')}")
    return 0


def cmd_installed(args: argparse.Namespace) -> int:
    installed = installed_as_list(state())
    if args.json:
        print(json.dumps({"apps": installed}, indent=2))
        return 0
    if not installed:
        print("No packages installed")
        return 0
    for item in installed:
        print(f"{item.get('id','?'):<20} {item.get('version','?'):<10} {item.get('name','')}")
    return 0


def cmd_install(args: argparse.Namespace) -> int:
    try:
        result, snap_id = with_transaction(
            reason=f"install:{args.package_id}",
            action=lambda: install_app(args.package_id, force=args.force, no_verify=args.no_verify),
        )
    except Exception as exc:
        print(f"install failed: {exc}", file=sys.stderr)
        return 1

    payload = {"snapshot": snap_id, **result}
    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        print(f"{result['status']}: {result['id']} {result['version']} (snapshot {snap_id})")
    return 0


def cmd_remove(args: argparse.Namespace) -> int:
    data = state()
    if args.package_id not in data.get("apps", {}):
        if args.json:
            print(json.dumps({"removed": False, "id": args.package_id}, indent=2))
        else:
            print(f"not installed: {args.package_id}")
        return 1

    try:
        result, snap_id = with_transaction(
            reason=f"remove:{args.package_id}",
            action=lambda: {"removed": remove_app(args.package_id, state()), "id": args.package_id},
        )
    except Exception as exc:
        print(f"remove failed: {exc}", file=sys.stderr)
        return 1

    payload = {"snapshot": snap_id, **result}
    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        print(f"removed: {args.package_id} (snapshot {snap_id})")
    return 0


def cmd_upgrade(args: argparse.Namespace) -> int:
    installed = installed_as_list(state())
    if not installed:
        print(json.dumps({"updated": []}, indent=2) if args.json else "No installed packages to upgrade")
        return 0

    try:
        repo = load_repo(require_signature=not args.no_verify)
    except Exception as exc:
        print(f"upgrade failed: {exc}", file=sys.stderr)
        if args.json:
            print(json.dumps({"updated": [], "error": str(exc)}, indent=2))
        return 1
    idx = package_index(repo)
    pending = []
    for item in installed:
        app_id = str(item.get("id", ""))
        installed_version = str(item.get("version", "0"))
        repo_item = idx.get(app_id)
        if repo_item is None:
            continue
        repo_version = str(repo_item.get("version", "0"))
        if version_key(repo_version) > version_key(installed_version):
            pending.append(app_id)

    if not pending:
        print(json.dumps({"updated": []}, indent=2) if args.json else "All installed packages are up to date")
        return 0

    def do_upgrade() -> dict:
        rows = []
        for app_id in pending:
            rows.append(install_app(app_id, force=True, no_verify=args.no_verify))
        return {"updated": rows}

    try:
        result, snap_id = with_transaction(reason="upgrade", action=do_upgrade)
    except Exception as exc:
        print(f"upgrade failed: {exc}", file=sys.stderr)
        return 1

    payload = {"snapshot": snap_id, **result}
    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        for row in result.get("updated", []):
            print(f"updated: {row['id']} -> {row['version']}")
        print(f"snapshot: {snap_id}")
    return 0


def cmd_history(args: argparse.Namespace) -> int:
    rows = list_snapshots()
    if args.limit > 0:
        rows = rows[: args.limit]
    if args.json:
        print(json.dumps({"snapshots": rows}, indent=2))
        return 0
    if not rows:
        print("No snapshots available")
        return 0
    for row in rows:
        print(f"{row.get('id',''):<24} {row.get('created_at',''):<24} {row.get('reason','')}")
    return 0


def cmd_rollback(args: argparse.Namespace) -> int:
    snap_id = args.snapshot_id
    if snap_id == "latest":
        rows = list_snapshots()
        if not rows:
            print("No snapshots available", file=sys.stderr)
            return 1
        snap_id = rows[0]["id"]

    try:
        result = restore_snapshot(snap_id)
    except Exception as exc:
        print(f"rollback failed: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(f"rolled back to {result['id']} ({result.get('reason','')})")
    return 0


def add_scope_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--scope", choices=("user", "system"), default="user", help="installation scope")


def add_repo_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--repo-root", help="signed repository root to use")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="crixapkg",
        description="CRIXA package manager for signed local repository packages",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_verify = sub.add_parser("verify", help="verify repo metadata signature")
    p_verify.add_argument("--json", action="store_true")
    add_repo_arg(p_verify)
    p_verify.set_defaults(func=cmd_verify)

    p_list = sub.add_parser("list", help="list available packages")
    p_list.add_argument("--json", action="store_true")
    p_list.add_argument("--no-verify", action="store_true", help="skip signature verification")
    add_repo_arg(p_list)
    p_list.set_defaults(func=cmd_list)

    p_installed = sub.add_parser("installed", help="list installed packages")
    p_installed.add_argument("--json", action="store_true")
    add_scope_arg(p_installed)
    p_installed.set_defaults(func=cmd_installed)

    p_install = sub.add_parser("install", help="install a package by id")
    p_install.add_argument("package_id")
    p_install.add_argument("--force", action="store_true")
    p_install.add_argument("--json", action="store_true")
    p_install.add_argument("--no-verify", action="store_true", help="skip signature verification")
    add_scope_arg(p_install)
    add_repo_arg(p_install)
    p_install.set_defaults(func=cmd_install)

    p_remove = sub.add_parser("remove", help="remove an installed package")
    p_remove.add_argument("package_id")
    p_remove.add_argument("--json", action="store_true")
    add_scope_arg(p_remove)
    p_remove.set_defaults(func=cmd_remove)

    p_upgrade = sub.add_parser("upgrade", help="upgrade installed packages to latest repo versions")
    p_upgrade.add_argument("--json", action="store_true")
    p_upgrade.add_argument("--no-verify", action="store_true", help="skip signature verification")
    add_scope_arg(p_upgrade)
    add_repo_arg(p_upgrade)
    p_upgrade.set_defaults(func=cmd_upgrade)

    p_history = sub.add_parser("history", help="show transaction snapshots")
    p_history.add_argument("--json", action="store_true")
    p_history.add_argument("--limit", type=int, default=30)
    add_scope_arg(p_history)
    p_history.set_defaults(func=cmd_history)

    p_rollback = sub.add_parser("rollback", help="rollback to a snapshot id or 'latest'")
    p_rollback.add_argument("snapshot_id", help="snapshot id or 'latest'")
    p_rollback.add_argument("--json", action="store_true")
    add_scope_arg(p_rollback)
    p_rollback.set_defaults(func=cmd_rollback)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    configure_scope(getattr(args, "scope", "user"))
    configure_repo(getattr(args, "repo_root", None))
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
