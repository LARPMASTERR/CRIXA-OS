#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

CATALOG_PATH="$PROJECT_ROOT/store-packages/catalog.json"
SYSTEM_ROLLOUTS_PATH="$PROJECT_ROOT/store-packages/system-rollouts.json"
SRC_PACKAGES_DIR="$PROJECT_ROOT/store-packages/packages"
REPO_ROOT="${REPO_ROOT:-$PROJECT_ROOT/crixa-repo}"
REPO_PACKAGES_DIR="$REPO_ROOT/packages"
REPO_METADATA_DIR="$REPO_ROOT/metadata"
REPO_KEYS_DIR="$REPO_ROOT/keys"

KEY_STORE_DIR="${KEY_STORE_DIR:-$PROJECT_ROOT/.secrets/repo-keys}"
PRIVATE_KEY="$KEY_STORE_DIR/crixa-repo-private.pem"
PUBLIC_KEY="$KEY_STORE_DIR/crixa-repo-public.pem"

PYTHON_BIN="${PYTHON_BIN:-python3}"

require_file() {
  local path="$1"
  [[ -f "$path" ]] || {
    echo "Missing required file: $path" >&2
    exit 1
  }
}

require_cmd() {
  local cmd="$1"
  command -v "$cmd" >/dev/null 2>&1 || {
    echo "Required command not found: $cmd" >&2
    exit 1
  }
}

main() {
  require_file "$CATALOG_PATH"
  require_file "$SYSTEM_ROLLOUTS_PATH"
  require_cmd "$PYTHON_BIN"
  require_cmd openssl

  mkdir -p "$KEY_STORE_DIR" "$REPO_PACKAGES_DIR" "$REPO_METADATA_DIR" "$REPO_KEYS_DIR"

  if [[ ! -f "$PRIVATE_KEY" ]]; then
    openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:4096 -out "$PRIVATE_KEY"
    chmod 0600 "$PRIVATE_KEY"
  fi

  openssl pkey -in "$PRIVATE_KEY" -pubout -out "$PUBLIC_KEY" >/dev/null 2>&1
  chmod 0644 "$PUBLIC_KEY"

  rm -f "$REPO_PACKAGES_DIR"/*.crixapkg

  export CATALOG_PATH SYSTEM_ROLLOUTS_PATH SRC_PACKAGES_DIR REPO_PACKAGES_DIR REPO_METADATA_DIR
  "$PYTHON_BIN" - <<'PY'
import hashlib
import json
import os
import tarfile
import tempfile
from datetime import datetime, timezone
from pathlib import Path

catalog_path = Path(os.environ["CATALOG_PATH"])
system_rollouts_path = Path(os.environ["SYSTEM_ROLLOUTS_PATH"])
src_packages_dir = Path(os.environ["SRC_PACKAGES_DIR"])
repo_packages_dir = Path(os.environ["REPO_PACKAGES_DIR"])
repo_metadata_dir = Path(os.environ["REPO_METADATA_DIR"])


def sha256sum(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            chunk = f.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
apps = catalog.get("apps", [])
if not isinstance(apps, list):
    raise SystemExit("catalog.json missing valid 'apps' list")

packages_meta = []
seen_ids: set[str] = set()

for app in apps:
    if not isinstance(app, dict):
        continue
    app_id = str(app.get("id", "")).strip()
    version = str(app.get("version", "")).strip()
    if not app_id or not version:
        continue
    if app_id in seen_ids:
        raise SystemExit(f"duplicate package id in catalog: {app_id}")
    seen_ids.add(app_id)

    payload_root = src_packages_dir / app_id / "payload"
    if not payload_root.is_dir():
        raise SystemExit(f"payload missing for {app_id}: {payload_root}")

    pkg_filename = f"{app_id}-{version}.crixapkg"
    pkg_path = repo_packages_dir / pkg_filename

    manifest = {
        "id": app_id,
        "name": app.get("name", app_id),
        "version": version,
        "arch": "all",
        "entrypoint": app.get("entrypoint", ""),
        "category": app.get("category", "General"),
        "summary": app.get("summary", ""),
        "description": app.get("description", ""),
        "features": app.get("features", []),
        "tags": app.get("tags", []),
        "payload_schema": "v1",
    }

    with tempfile.TemporaryDirectory(prefix="crixa-pkg-") as tmpdir:
        tmp = Path(tmpdir)
        manifest_path = tmp / "manifest.json"
        manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        payload_copy = tmp / "payload"
        payload_copy.mkdir(parents=True, exist_ok=True)
        for src in payload_root.rglob("*"):
            rel = src.relative_to(payload_root)
            dst = payload_copy / rel
            if src.is_dir():
                dst.mkdir(parents=True, exist_ok=True)
            else:
                dst.parent.mkdir(parents=True, exist_ok=True)
                dst.write_bytes(src.read_bytes())
        with tarfile.open(pkg_path, "w:gz", compresslevel=9, format=tarfile.PAX_FORMAT) as tar:
            tar.add(manifest_path, arcname="manifest.json", recursive=False)
            tar.add(payload_copy, arcname="payload", recursive=True)

    packages_meta.append(
        {
            "id": app_id,
            "name": app.get("name", app_id),
            "version": version,
            "category": app.get("category", "General"),
            "size_hint": app.get("size", ""),
            "summary": app.get("summary", ""),
            "description": app.get("description", ""),
            "entrypoint": app.get("entrypoint", ""),
            "features": app.get("features", []),
            "tags": app.get("tags", []),
            "filename": pkg_filename,
            "size_bytes": pkg_path.stat().st_size,
            "sha256": sha256sum(pkg_path),
        }
    )

repo_index = {
    "repo": "CRIXA Main",
    "format": 1,
    "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    "packages": sorted(packages_meta, key=lambda x: str(x.get("name", "")).lower()),
}

repo_metadata_dir.mkdir(parents=True, exist_ok=True)
(repo_metadata_dir / "repo.json").write_text(
    json.dumps(repo_index, indent=2, sort_keys=False) + "\n",
    encoding="utf-8",
)

rollouts_src = json.loads(system_rollouts_path.read_text(encoding="utf-8"))
tracks = rollouts_src.get("tracks", {})
if not isinstance(tracks, dict):
    raise SystemExit("system-rollouts.json missing 'tracks' object")

normalized_tracks: dict[str, dict] = {}
for track_name, raw in tracks.items():
    if not isinstance(track_name, str) or not isinstance(raw, dict):
        continue
    release_version = str(raw.get("release_version", "")).strip()
    if not release_version:
        continue
    rollout_percent = float(raw.get("rollout_percent", 100))
    rollout_percent = max(0.0, min(100.0, rollout_percent))
    normalized_tracks[track_name] = {
        "release_version": release_version,
        "min_current_version": str(raw.get("min_current_version", "0.0.0")).strip() or "0.0.0",
        "rollout_percent": rollout_percent,
        "deadline_utc": raw.get("deadline_utc"),
        "notes": str(raw.get("notes", "")),
        "payload": raw.get("payload", {}),
    }

if not normalized_tracks:
    raise SystemExit("system-rollouts.json has no valid track definitions")

system_updates = {
    "product": str(rollouts_src.get("product", "CRIXA OS")),
    "schema": int(rollouts_src.get("schema", 1)),
    "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    "tracks": normalized_tracks,
}
(repo_metadata_dir / "system-updates.json").write_text(
    json.dumps(system_updates, indent=2, sort_keys=False) + "\n",
    encoding="utf-8",
)
PY

  openssl dgst -sha256 -sign "$PRIVATE_KEY" -out "$REPO_METADATA_DIR/repo.sig" "$REPO_METADATA_DIR/repo.json"
  openssl dgst -sha256 -sign "$PRIVATE_KEY" -out "$REPO_METADATA_DIR/system-updates.sig" "$REPO_METADATA_DIR/system-updates.json"
  install -m 0644 "$PUBLIC_KEY" "$REPO_KEYS_DIR/repo-public.pem"
  install -m 0644 "$CATALOG_PATH" "$REPO_ROOT/catalog.json"
}

main "$@"
