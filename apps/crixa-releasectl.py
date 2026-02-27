#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import socket
import subprocess
import sys
from pathlib import Path

LOCAL_RELEASE = Path("/etc/crixa-release.json")
REPO_UPDATES = Path("/usr/share/crixa-repo/metadata/system-updates.json")
REPO_UPDATES_SIG = Path("/usr/share/crixa-repo/metadata/system-updates.sig")
REPO_PUBLIC_KEY = Path("/usr/share/crixa-repo/keys/repo-public.pem")

DEFAULT_RELEASE = {
    "product": "CRIXA OS",
    "version": "0.0.0",
    "track": "stable",
    "build_id": "unknown",
}


def load_json(path: Path, default: dict) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return dict(default)


def save_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def version_key(version: str) -> tuple:
    parts = []
    token = ""
    for ch in version:
        if ch.isalnum():
            token += ch
        else:
            if token:
                parts.append(token)
            token = ""
    if token:
        parts.append(token)
    key = []
    for part in parts:
        if part.isdigit():
            key.append((0, int(part)))
        else:
            key.append((1, part.lower()))
    return tuple(key)


def verify_updates_signature() -> tuple[bool, str]:
    for required in (REPO_UPDATES, REPO_UPDATES_SIG, REPO_PUBLIC_KEY):
        if not required.exists():
            return False, f"missing file: {required}"
    cmd = [
        "openssl",
        "dgst",
        "-sha256",
        "-verify",
        str(REPO_PUBLIC_KEY),
        "-signature",
        str(REPO_UPDATES_SIG),
        str(REPO_UPDATES),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        return False, (result.stderr or result.stdout).strip() or "signature verification failed"
    return True, "ok"


def machine_identity(explicit: str = "") -> str:
    if explicit:
        return explicit
    for path in (Path("/etc/machine-id"), Path("/var/lib/dbus/machine-id")):
        try:
            value = path.read_text(encoding="utf-8").strip()
            if value:
                return value
        except Exception:
            pass
    return socket.gethostname() or "unknown-host"


def rollout_bucket(track: str, release_version: str, machine_id: str) -> float:
    seed = f"{track}:{release_version}:{machine_id}".encode("utf-8")
    digest = hashlib.sha256(seed).hexdigest()
    raw = int(digest[:8], 16)
    return (raw % 10000) / 100.0


def read_local_release() -> dict:
    data = load_json(LOCAL_RELEASE, DEFAULT_RELEASE)
    out = dict(DEFAULT_RELEASE)
    out.update(
        {
            "product": str(data.get("product", DEFAULT_RELEASE["product"])),
            "version": str(data.get("version", DEFAULT_RELEASE["version"])),
            "track": str(data.get("track", DEFAULT_RELEASE["track"])).lower(),
            "build_id": str(data.get("build_id", DEFAULT_RELEASE["build_id"])),
        }
    )
    return out


def read_updates_manifest(require_signature: bool) -> dict:
    if require_signature:
        ok, reason = verify_updates_signature()
        if not ok:
            raise RuntimeError(f"system updates metadata signature invalid: {reason}")
    data = load_json(REPO_UPDATES, {"tracks": {}})
    tracks = data.get("tracks", {})
    if not isinstance(tracks, dict):
        raise RuntimeError("invalid updates metadata: 'tracks' must be an object")
    return data


def evaluate_release(
    *,
    current_version: str,
    track: str,
    machine_id: str,
    manifest: dict,
) -> dict:
    tracks = manifest.get("tracks", {})
    track_payload = tracks.get(track)
    if not isinstance(track_payload, dict):
        return {
            "track": track,
            "eligible": False,
            "up_to_date": True,
            "reason": "track_not_defined",
            "release_version": current_version,
            "rollout_percent": 0.0,
            "bucket_percent": 0.0,
            "payload": {},
            "notes": "",
        }

    release_version = str(track_payload.get("release_version", current_version))
    min_current = str(track_payload.get("min_current_version", "0.0.0"))
    rollout_percent = float(track_payload.get("rollout_percent", 100.0))
    rollout_percent = max(0.0, min(100.0, rollout_percent))
    notes = str(track_payload.get("notes", ""))
    payload = track_payload.get("payload", {})
    if not isinstance(payload, dict):
        payload = {}

    if version_key(current_version) >= version_key(release_version):
        return {
            "track": track,
            "eligible": False,
            "up_to_date": True,
            "reason": "already_current_or_newer",
            "release_version": release_version,
            "rollout_percent": rollout_percent,
            "bucket_percent": 0.0,
            "payload": payload,
            "notes": notes,
            "min_current_version": min_current,
        }

    if version_key(current_version) < version_key(min_current):
        return {
            "track": track,
            "eligible": False,
            "up_to_date": False,
            "reason": "min_current_version_not_met",
            "release_version": release_version,
            "rollout_percent": rollout_percent,
            "bucket_percent": 0.0,
            "payload": payload,
            "notes": notes,
            "min_current_version": min_current,
        }

    bucket = rollout_bucket(track, release_version, machine_id)
    eligible = bucket < rollout_percent
    return {
        "track": track,
        "eligible": eligible,
        "up_to_date": False,
        "reason": "eligible_for_rollout" if eligible else "outside_rollout_percentage",
        "release_version": release_version,
        "rollout_percent": rollout_percent,
        "bucket_percent": round(bucket, 2),
        "payload": payload,
        "notes": notes,
        "min_current_version": min_current,
    }


def require_root() -> None:
    if os.geteuid() != 0:
        raise RuntimeError("root privileges are required for this operation")


def cmd_verify(args: argparse.Namespace) -> int:
    ok, reason = verify_updates_signature()
    payload = {"ok": ok, "message": reason}
    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        print("ok" if ok else f"failed: {reason}")
    return 0 if ok else 2


def cmd_status(args: argparse.Namespace) -> int:
    local = read_local_release()
    track = (args.track or local.get("track", "stable")).lower()
    machine_id = machine_identity(args.machine_id or "")
    try:
        manifest = read_updates_manifest(require_signature=not args.no_verify)
    except Exception as exc:
        if args.json:
            print(
                json.dumps(
                    {
                        "ok": False,
                        "error": str(exc),
                        "current": local,
                    },
                    indent=2,
                )
            )
            return 1
        print(f"status failed: {exc}", file=sys.stderr)
        return 1

    status = evaluate_release(
        current_version=str(local.get("version", "0.0.0")),
        track=track,
        machine_id=machine_id,
        manifest=manifest,
    )
    payload = {
        "ok": True,
        "current": local,
        "manifest_generated_at": str(manifest.get("generated_at", "")),
        "machine_id_hash": hashlib.sha256(machine_id.encode("utf-8")).hexdigest()[:12],
        "status": status,
    }
    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        print(f"track: {track}")
        print(f"current: {local.get('version')}")
        print(f"target: {status.get('release_version')}")
        print(f"eligible: {status.get('eligible')}")
        print(f"reason: {status.get('reason')}")
        print(f"rollout: {status.get('rollout_percent')}%  bucket: {status.get('bucket_percent')}%")
    return 0


def cmd_switch_track(args: argparse.Namespace) -> int:
    track = args.track.lower().strip()
    try:
        require_root()
    except Exception as exc:
        print(f"switch-track failed: {exc}", file=sys.stderr)
        return 1

    local = read_local_release()
    local["track"] = track
    save_json(LOCAL_RELEASE, local)
    payload = {"updated": True, "track": track, "version": local.get("version", "0.0.0")}
    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        print(f"track set to: {track}")
    return 0


def cmd_set_version(args: argparse.Namespace) -> int:
    try:
        require_root()
    except Exception as exc:
        print(f"set-version failed: {exc}", file=sys.stderr)
        return 1

    local = read_local_release()
    local["version"] = args.version
    if args.build_id:
        local["build_id"] = args.build_id
    save_json(LOCAL_RELEASE, local)
    payload = {"updated": True, "version": local["version"], "build_id": local.get("build_id", "")}
    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        print(f"version set to: {local['version']}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="crixa-releasectl",
        description="CRIXA system release channel and rollout controller",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_verify = sub.add_parser("verify", help="verify signed system updates metadata")
    p_verify.add_argument("--json", action="store_true")
    p_verify.set_defaults(func=cmd_verify)

    p_status = sub.add_parser("status", help="show rollout eligibility for current system")
    p_status.add_argument("--track", default="", help="override track for this query")
    p_status.add_argument("--machine-id", default="", help="override machine id for testing rollout buckets")
    p_status.add_argument("--no-verify", action="store_true", help="skip signature verification")
    p_status.add_argument("--json", action="store_true")
    p_status.set_defaults(func=cmd_status)

    p_switch = sub.add_parser("switch-track", help="change local update track")
    p_switch.add_argument("track", help="channel name (stable/beta/canary/etc)")
    p_switch.add_argument("--json", action="store_true")
    p_switch.set_defaults(func=cmd_switch_track)

    p_set = sub.add_parser("set-version", help="set local OS version/build id after applying an update")
    p_set.add_argument("version")
    p_set.add_argument("--build-id", default="")
    p_set.add_argument("--json", action="store_true")
    p_set.set_defaults(func=cmd_set_version)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
