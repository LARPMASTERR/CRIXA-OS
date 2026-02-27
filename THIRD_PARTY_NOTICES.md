# Third-Party Notices

This file documents major third-party software and content used by CRIXA OS.

## Software Stack

CRIXA OS is assembled from Debian packages and upstream open-source projects, including but not limited to:

- Debian GNU/Linux base system
- Linux kernel
- GNU GRUB
- X.Org
- Openbox
- tint2
- rofi
- Thunar
- Firefox ESR
- NetworkManager
- Flatpak

License terms for these components are provided by their upstream projects and Debian packaging metadata. In built systems, see `/usr/share/doc/<package>/copyright`.

## Wallpaper Assets

Wallpapers under `assets/wallpapers/` use NASA image sources. Attribution and source links are listed in:

- `assets/wallpapers/ATTRIBUTION.txt`

NASA imagery is generally public domain in the United States, subject to NASA media usage guidance.

## Icon Assets

Icons under `assets/icons/` are original CRIXA project artwork and are released under CC0-1.0:

- `assets/icons/LICENSE.txt`

## Distribution Note

This repository is source-first. Generated live images and root filesystem snapshots are excluded by `.gitignore` and should be built locally from scripts in `build/`.
