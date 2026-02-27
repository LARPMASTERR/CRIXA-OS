#!/usr/bin/env python3
from __future__ import annotations

import json
import sys


def respond(payload: dict, code: int = 0) -> None:
    print(json.dumps(payload))
    raise SystemExit(code)


def load_request() -> dict:
    raw = sys.stdin.read()
    if not raw.strip():
        return {}
    try:
        req = json.loads(raw)
    except json.JSONDecodeError:
        respond({"ok": False, "error": "invalid JSON"}, 2)
    if not isinstance(req, dict):
        respond({"ok": False, "error": "request must be object"}, 2)
    return req


def main() -> int:
    req = load_request()
    action = str(req.get("action", "")).lower()
    query = str(req.get("query", "")).lower()

    if action in ("list", "search"):
        apps = [
            {
                "id": "example.hello",
                "name": "Hello Extension App",
                "version": "0.1.0",
                "category": "Example",
                "summary": "Template app from extension backend",
                "description": "Replace this with real source logic.",
                "features": ["custom backend protocol", "third-party extension support"],
                "installed": False,
                "source": "example-backend",
            }
        ]
        if query:
            apps = [app for app in apps if query in app["name"].lower() or query in app["id"].lower()]
        respond({"ok": True, "apps": apps, "message": "template backend"})

    if action == "capabilities":
        respond({"ok": True, "capabilities": ["list"]})

    respond({"ok": False, "error": f"unsupported action: {action}"}, 2)


if __name__ == "__main__":
    raise SystemExit(main())
