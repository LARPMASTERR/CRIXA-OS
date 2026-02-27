# Security Policy

## Supported Scope

Security reports are accepted for:

- Build scripts in `build/`
- Custom CRIXA apps in `apps/`
- Store backend logic in `store-backends/`
- Packaging/release logic in this repository

## Reporting a Vulnerability

Please report vulnerabilities privately before public disclosure.

Include:

1. Impact summary
2. Reproduction steps
3. Affected files/commands
4. Suggested remediation (if available)

## Sensitive Data Rules for Contributors

- Never commit private keys, credentials, or access tokens.
- Never commit machine-specific personal paths or usernames.
- Keep generated artifacts (`rootfs/`, `iso/`, `logs/`, `build/work/`, `crixa-repo/`) out of source control.
- Store local signing keys under `.secrets/` only (already git-ignored).
