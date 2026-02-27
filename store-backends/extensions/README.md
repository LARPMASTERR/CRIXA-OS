# CRIXA Store Extension Backends

CRIXA Store loads backend manifests from:

- `/usr/share/crixa-store/backends` (system)
- `~/.local/share/crixa-store/backends` (user)
- `~/.config/crixa-store/backends` (user)

Drop a manifest `.json` and executable command script into one of those directories to add a new app source.

## Manifest Schema

```json
{
  "id": "example-backend",
  "name": "Example Backend",
  "command": "/absolute/path/to/backend-script.py",
  "priority": 50,
  "supports_upgrade": true,
  "description": "Short source description"
}
```

Fields:

- `id`: unique backend id
- `name`: display name in Store source picker
- `command`: executable path (absolute recommended)
- `priority`: lower appears earlier in source list
- `supports_upgrade`: whether `Upgrade Source` button should be enabled
- `description`: optional human-readable details

## Backend Protocol

CRIXA Store sends a JSON request on `stdin`. Backend must write JSON response to `stdout`.

### Request

```json
{
  "action": "list|install|remove|launch|upgrade|capabilities",
  "query": "optional search text",
  "app_id": "optional app id",
  "force": false,
  "limit": 240
}
```

### Response

```json
{
  "ok": true,
  "message": "optional status text",
  "apps": [
    {
      "id": "com.example.App",
      "name": "Example App",
      "version": "1.2.3",
      "category": "Utility",
      "summary": "Short text",
      "description": "Long text",
      "features": ["optional", "list"],
      "size": "optional",
      "installed": false,
      "source": "example-backend"
    }
  ]
}
```

If `ok=false`, include `error` or `message`.

## Security Guidance

- Treat backend command as trusted code.
- Prefer dedicated non-root commands.
- Avoid shell interpolation with user input.
- Validate app ids/arguments before install/remove operations.

See `example-template.py` for a minimal starter backend.
