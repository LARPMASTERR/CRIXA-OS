# CRIXA OS Legal Coverage

This document defines the legal and distribution model for this repository.

## Scope

- The source code in this repository is licensed under the MIT license in [`LICENSE`](LICENSE).
- Generated artifacts are intentionally excluded from source control (for example `rootfs/`, `iso/`, `logs/`, and build work directories).
- Private signing keys are intentionally excluded from source control.

## Third-Party Components

CRIXA OS builds and redistributes software from upstream projects (for example Debian packages, Linux kernel, GRUB, Openbox, tint2, rofi, Thunar, Firefox, and others). Each upstream component keeps its own license terms.

- Upstream package licensing for Debian-delivered components is available in the built system under `/usr/share/doc/<package>/copyright`.
- Source archive obligations and notices are delegated to the original upstream projects and Debian packaging metadata.
- A high-level notice list is maintained in [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md).

## Visual Assets

- Wallpapers in `assets/wallpapers/` use NASA image sources and attribution recorded in `assets/wallpapers/ATTRIBUTION.txt`.
- Icons in `assets/icons/` are original CRIXA assets and released under CC0-1.0 per `assets/icons/LICENSE.txt`.

## Trademarks

"CRIXA" and "CRIXA OS" may be used for this project and forks unless restricted by future trademark policy. Third-party marks (for example "Debian", "Firefox", "NVIDIA", "AMD") remain property of their respective owners.

## Security and Signing Material

- Never commit private keys, tokens, credentials, or personally identifying path data.
- Default signing key location is `.secrets/repo-keys/` and is git-ignored.
- Public metadata and signatures may be generated during build and are treated as build output.

## Compliance Checklist Before Publishing

1. Ensure no private keys are present in tracked files.
2. Ensure no personal usernames or local absolute paths are embedded.
3. Ensure third-party assets have attribution/license records.
4. Ensure generated binaries/artifacts are excluded.

CRIXA OS is provided “as is”, without warranty of any kind, express or implied. The maintainers are not liable for any damages, data loss, hardware malfunction, or security compromise arising from its use.