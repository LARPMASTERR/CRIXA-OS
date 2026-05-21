#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

try:
    from PySide2 import QtCore, QtGui, QtWidgets

    QT_IMPORT_ERROR: Exception | None = None
except Exception as exc:  # pragma: no cover - runtime fallback path.
    QtCore = None
    QtGui = None
    QtWidgets = None
    QT_IMPORT_ERROR = exc


APP_NAME = "CRIXA Welcome"
CONFIG_HOME = Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config")))
STATE_DIR = CONFIG_HOME / "crixa-welcome"
SEEN_MARKER = STATE_DIR / "seen-v1.done"
DEV_ROOT = Path(__file__).resolve().parents[1] if Path(__file__).resolve().parent.name == "apps" else None


@dataclass(frozen=True, slots=True)
class LaunchAction:
    action_id: str
    title: str
    subtitle: str
    command: tuple[str, ...]
    icon: str
    accent: str


PRIMARY_ACTIONS = [
    LaunchAction("orbit", "Open Orbit", "Command deck and app search", ("crixa-menu",), "crixa-launcher", "#35c9ba"),
    LaunchAction("customize", "Customize", "Display, theme, panel, and system controls", ("crixa-settings",), "preferences-system", "#75a7ff"),
    LaunchAction("install", "Install CRIXA", "Write CRIXA OS to disk", ("crixa-installer",), "drive-harddisk", "#f2b84b"),
    LaunchAction("updates", "Check Updates", "Release tracks and rollback snapshots", ("crixa-updater",), "system-software-update", "#8ee0c8"),
    LaunchAction("apps", "Browse Apps", "Curated CRIXA software", ("crixa-store",), "system-software-install", "#b69cff"),
    LaunchAction(
        "wallpaper",
        "Choose Wallpaper",
        "Installed background collection",
        ("crixa-files", "/usr/share/backgrounds/crixa"),
        "preferences-desktop-wallpaper",
        "#f08ca3",
    ),
]

EXPLORE_ACTIONS = [
    LaunchAction("console", "Console", "Terminal workspace", ("crixa-terminal",), "utilities-terminal", "#35c9ba"),
    LaunchAction("files", "Hangar", "Files and folders", ("crixa-files",), "system-file-manager", "#75a7ff"),
    LaunchAction("browser", "Navigator", "Web workspace", ("crixa-browser",), "firefox-esr", "#f2b84b"),
    LaunchAction("pulse", "Pulse", "System monitor", ("crixa-task-manager",), "utilities-system-monitor", "#8ee0c8"),
]

REQUIRED_COMMANDS = sorted({action.command[0] for action in [*PRIMARY_ACTIONS, *EXPLORE_ACTIONS]})
DESKTOP_ENTRY = Path("/usr/share/applications/crixa-welcome.desktop")


def build_path() -> str:
    entries = [
        str(Path.home() / ".local" / "bin"),
        "/usr/local/bin",
        "/usr/bin",
        "/bin",
    ]
    if DEV_ROOT is not None:
        entries.append(str(DEV_ROOT / "apps"))
    current = os.environ.get("PATH", "")
    if current:
        entries.extend(current.split(os.pathsep))

    deduped: list[str] = []
    seen: set[str] = set()
    for entry in entries:
        if entry and entry not in seen:
            deduped.append(entry)
            seen.add(entry)
    return os.pathsep.join(deduped)


def find_executable(program: str, path_value: str | None = None) -> str | None:
    if "/" in program:
        candidate = Path(program)
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)
        return None

    for directory in (path_value or build_path()).split(os.pathsep):
        if not directory:
            continue
        candidate = Path(directory) / program
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)

    if DEV_ROOT is not None:
        for suffix in ("", ".sh", ".py"):
            candidate = DEV_ROOT / "apps" / f"{program}{suffix}"
            if candidate.is_file():
                return str(candidate)
    return None


def write_seen_marker() -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    SEEN_MARKER.write_text(datetime.now().isoformat(timespec="seconds") + "\n", encoding="utf-8")


def state_is_seen() -> bool:
    return SEEN_MARKER.exists()


def launch_command(command: tuple[str, ...], env: dict[str, str]) -> tuple[bool, str]:
    if not command:
        return False, "No command configured"

    resolved = list(command)
    executable = resolved[0]
    if "/" not in executable:
        found = find_executable(executable, env.get("PATH"))
        if found is None:
            return False, f"Could not find command: {executable}"
        if DEV_ROOT is not None and found.endswith(".py"):
            resolved = [sys.executable, found, *resolved[1:]]
        elif DEV_ROOT is not None and found.endswith(".sh"):
            resolved = ["bash", found, *resolved[1:]]
        else:
            resolved[0] = found

    try:
        subprocess.Popen(resolved, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    except Exception as exc:
        return False, f"Could not launch {Path(resolved[0]).name}: {exc}"
    return True, ""


if QtWidgets is not None:

    class ActionCard(QtWidgets.QFrame):
        clicked = QtCore.Signal(object)

        def __init__(self, action: LaunchAction, compact: bool = False, parent: QtWidgets.QWidget | None = None) -> None:
            super().__init__(parent)
            self.action = action
            self.setObjectName("ActionCardCompact" if compact else "ActionCard")
            self.setCursor(QtCore.Qt.PointingHandCursor)
            self.setMinimumHeight(78 if compact else 96)
            self.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)

            layout = QtWidgets.QHBoxLayout(self)
            layout.setContentsMargins(14, 12, 14, 12)
            layout.setSpacing(12)

            badge = QtWidgets.QFrame()
            badge.setObjectName("IconBadge")
            badge.setStyleSheet(f"QFrame#IconBadge {{ background: {action.accent}; border-radius: 18px; }}")
            badge.setFixedSize(36, 36)
            badge_layout = QtWidgets.QVBoxLayout(badge)
            badge_layout.setContentsMargins(0, 0, 0, 0)
            icon_label = QtWidgets.QLabel()
            icon_label.setPixmap(icon_for_name(action.icon).pixmap(22, 22))
            icon_label.setAlignment(QtCore.Qt.AlignCenter)
            badge_layout.addWidget(icon_label)
            layout.addWidget(badge)

            text_layout = QtWidgets.QVBoxLayout()
            text_layout.setSpacing(3)
            title = QtWidgets.QLabel(action.title)
            title.setObjectName("CardTitle")
            subtitle = QtWidgets.QLabel(action.subtitle)
            subtitle.setObjectName("CardSubtitle")
            subtitle.setWordWrap(True)
            text_layout.addWidget(title)
            text_layout.addWidget(subtitle)
            layout.addLayout(text_layout, 1)

        def mouseReleaseEvent(self, event: QtGui.QMouseEvent) -> None:
            if event.button() == QtCore.Qt.LeftButton and self.rect().contains(event.pos()):
                self.clicked.emit(self.action)
            super().mouseReleaseEvent(event)


    class ChecklistRow(QtWidgets.QFrame):
        clicked = QtCore.Signal(object)

        def __init__(self, action: LaunchAction, parent: QtWidgets.QWidget | None = None) -> None:
            super().__init__(parent)
            self.action = action
            self.setObjectName("ChecklistRow")
            self.setCursor(QtCore.Qt.PointingHandCursor)

            layout = QtWidgets.QHBoxLayout(self)
            layout.setContentsMargins(12, 10, 12, 10)
            layout.setSpacing(10)
            mark = QtWidgets.QLabel(">")
            mark.setObjectName("ChecklistMark")
            mark.setAlignment(QtCore.Qt.AlignCenter)
            mark.setFixedWidth(18)
            layout.addWidget(mark)

            text = QtWidgets.QVBoxLayout()
            text.setSpacing(1)
            title = QtWidgets.QLabel(action.title)
            title.setObjectName("ChecklistTitle")
            subtitle = QtWidgets.QLabel(action.subtitle)
            subtitle.setObjectName("ChecklistSubtitle")
            text.addWidget(title)
            text.addWidget(subtitle)
            layout.addLayout(text, 1)

        def mouseReleaseEvent(self, event: QtGui.QMouseEvent) -> None:
            if event.button() == QtCore.Qt.LeftButton and self.rect().contains(event.pos()):
                self.clicked.emit(self.action)
            super().mouseReleaseEvent(event)


    class WelcomeHub(QtWidgets.QWidget):
        def __init__(self, first_run: bool) -> None:
            super().__init__()
            self.first_run = first_run
            self.env = os.environ.copy()
            self.env["PATH"] = build_path()

            self.setWindowTitle(APP_NAME)
            self.setMinimumSize(1060, 680)
            self.resize(1160, 740)
            self._build_ui()
            self._position_window()

        def _build_ui(self) -> None:
            root = QtWidgets.QVBoxLayout(self)
            root.setContentsMargins(18, 18, 18, 18)
            root.setSpacing(14)

            shell = QtWidgets.QFrame()
            shell.setObjectName("Shell")
            root.addWidget(shell)
            layout = QtWidgets.QVBoxLayout(shell)
            layout.setContentsMargins(18, 18, 18, 18)
            layout.setSpacing(14)

            header = QtWidgets.QFrame()
            header.setObjectName("Hero")
            hero_layout = QtWidgets.QHBoxLayout(header)
            hero_layout.setContentsMargins(22, 18, 18, 18)
            hero_layout.setSpacing(16)

            hero_copy = QtWidgets.QVBoxLayout()
            hero_copy.setSpacing(4)
            eyebrow = QtWidgets.QLabel("CRIXA OS v0")
            eyebrow.setObjectName("Eyebrow")
            title = QtWidgets.QLabel("Welcome")
            title.setObjectName("HeroTitle")
            subtitle = QtWidgets.QLabel("Your system is ready.")
            subtitle.setObjectName("HeroSubtitle")
            hero_copy.addWidget(eyebrow)
            hero_copy.addWidget(title)
            hero_copy.addWidget(subtitle)
            hero_layout.addLayout(hero_copy, 1)

            meta = QtWidgets.QVBoxLayout()
            meta.setSpacing(4)
            for label in self.status_lines():
                row = QtWidgets.QLabel(label)
                row.setObjectName("HeroMeta")
                row.setAlignment(QtCore.Qt.AlignRight)
                meta.addWidget(row)
            hero_layout.addLayout(meta)
            layout.addWidget(header)

            body = QtWidgets.QHBoxLayout()
            body.setSpacing(14)
            layout.addLayout(body, 1)

            left = QtWidgets.QFrame()
            left.setObjectName("Panel")
            left_layout = QtWidgets.QVBoxLayout(left)
            left_layout.setContentsMargins(16, 16, 16, 16)
            left_layout.setSpacing(12)
            title = QtWidgets.QLabel("Start Here")
            title.setObjectName("SectionTitle")
            left_layout.addWidget(title)
            for action in PRIMARY_ACTIONS:
                row = ChecklistRow(action)
                row.clicked.connect(self.launch_action)
                left_layout.addWidget(row)
            left_layout.addStretch(1)
            body.addWidget(left, 4)

            right = QtWidgets.QFrame()
            right.setObjectName("Panel")
            right_layout = QtWidgets.QVBoxLayout(right)
            right_layout.setContentsMargins(16, 16, 16, 16)
            right_layout.setSpacing(12)

            quick_title = QtWidgets.QLabel("Quick Actions")
            quick_title.setObjectName("SectionTitle")
            right_layout.addWidget(quick_title)
            grid = QtWidgets.QGridLayout()
            grid.setSpacing(10)
            for index, action in enumerate(PRIMARY_ACTIONS[:4]):
                card = ActionCard(action, compact=True)
                card.clicked.connect(self.launch_action)
                grid.addWidget(card, index // 2, index % 2)
            right_layout.addLayout(grid)

            explore_title = QtWidgets.QLabel("Explore CRIXA")
            explore_title.setObjectName("SectionTitle")
            right_layout.addWidget(explore_title)
            explore_grid = QtWidgets.QGridLayout()
            explore_grid.setSpacing(10)
            for index, action in enumerate(EXPLORE_ACTIONS):
                card = ActionCard(action, compact=True)
                card.clicked.connect(self.launch_action)
                explore_grid.addWidget(card, index // 2, index % 2)
            right_layout.addLayout(explore_grid)

            self.status = QtWidgets.QLabel("Welcome ready")
            self.status.setObjectName("Status")
            self.status.setWordWrap(True)
            right_layout.addWidget(self.status)

            footer = QtWidgets.QHBoxLayout()
            footer.setSpacing(10)
            dont_show = QtWidgets.QPushButton("Don't Show Again")
            dont_show.setObjectName("SecondaryButton")
            dont_show.clicked.connect(self.mark_seen_and_close)
            close = QtWidgets.QPushButton("Close")
            close.setObjectName("SecondaryButton")
            close.clicked.connect(self.close)
            footer.addStretch(1)
            footer.addWidget(dont_show)
            footer.addWidget(close)
            right_layout.addLayout(footer)
            body.addWidget(right, 6)

            self.apply_style()

        def status_lines(self) -> list[str]:
            session = os.environ.get("XDG_SESSION_TYPE") or os.environ.get("XDG_CURRENT_DESKTOP") or "desktop"
            mode = "First login" if self.first_run else "Manual launch"
            return [
                f"Session: {session}",
                f"Mode: {mode}",
                f"Profile: {Path.home().name}",
            ]

        def apply_style(self) -> None:
            self.setStyleSheet(
                """
                QWidget {
                    background: #0b0f14;
                    color: #eef4f2;
                    font-family: "IBM Plex Sans", "DejaVu Sans", sans-serif;
                    font-size: 10pt;
                    letter-spacing: 0;
                }
                QFrame#Shell {
                    background: #0e1117;
                    border: 1px solid #33414a;
                    border-radius: 18px;
                }
                QFrame#Hero {
                    background: #171d24;
                    border: 1px solid #31404a;
                    border-radius: 14px;
                }
                QFrame#Panel {
                    background: #151b22;
                    border: 1px solid #2d3942;
                    border-radius: 12px;
                }
                QLabel#Eyebrow {
                    color: #35c9ba;
                    font-size: 10pt;
                    font-weight: 700;
                }
                QLabel#HeroTitle {
                    color: #ffffff;
                    font-size: 30pt;
                    font-weight: 800;
                }
                QLabel#HeroSubtitle {
                    color: #aab7b5;
                    font-size: 13pt;
                }
                QLabel#HeroMeta, QLabel#Status {
                    color: #9ba8a7;
                }
                QFrame#Hero QLabel, QFrame#Panel QLabel, QFrame#ChecklistRow QLabel, QFrame#ActionCardCompact QLabel {
                    background: transparent;
                }
                QLabel#SectionTitle {
                    color: #f4fbf9;
                    font-size: 13pt;
                    font-weight: 800;
                }
                QFrame#ChecklistRow, QFrame#ActionCardCompact {
                    background: #202832;
                    border: 1px solid #34414a;
                    border-radius: 10px;
                }
                QFrame#ChecklistRow:hover, QFrame#ActionCardCompact:hover {
                    background: #263340;
                    border: 1px solid #35c9ba;
                }
                QLabel#ChecklistMark {
                    color: #35c9ba;
                    font-size: 17pt;
                    font-weight: 900;
                }
                QLabel#ChecklistTitle, QLabel#CardTitle {
                    color: #f6fbf9;
                    font-size: 11pt;
                    font-weight: 800;
                }
                QLabel#ChecklistSubtitle, QLabel#CardSubtitle {
                    color: #a4b1af;
                    font-size: 9pt;
                }
                QPushButton#SecondaryButton {
                    background: #202832;
                    border: 1px solid #34414a;
                    border-radius: 9px;
                    color: #eef4f2;
                    padding: 9px 14px;
                    font-weight: 700;
                }
                QPushButton#SecondaryButton:hover {
                    background: #2b3844;
                    border: 1px solid #35c9ba;
                }
                """
            )

        def _position_window(self) -> None:
            screen = QtWidgets.QApplication.primaryScreen()
            if not screen:
                return
            available = screen.availableGeometry()
            width = min(self.width(), max(900, int(available.width() * 0.82)))
            height = min(self.height(), max(620, int(available.height() * 0.82)))
            x = available.x() + max(12, (available.width() - width) // 2)
            y = available.y() + max(12, (available.height() - height) // 2)
            self.setGeometry(x, y, width, height)

        def launch_action(self, action: LaunchAction) -> None:
            ok, message = launch_command(action.command, self.env)
            if ok:
                self.status.setText(f"Opened {action.title}")
                return
            self.status.setText(f"Could not open {action.title}: {message}")

        def mark_seen_and_close(self) -> None:
            try:
                write_seen_marker()
            except Exception as exc:
                self.status.setText(f"Could not update first-run state: {exc}")
                return
            self.close()


def icon_for_name(name: str):
    if QtGui is None:
        return None
    if name:
        icon = QtGui.QIcon.fromTheme(name)
        if not icon.isNull():
            return icon
    fallback = QtGui.QIcon.fromTheme("application-x-executable")
    if not fallback.isNull():
        return fallback
    return QtWidgets.QApplication.style().standardIcon(QtWidgets.QStyle.SP_FileIcon)


def self_test() -> int:
    failures: list[str] = []
    if QT_IMPORT_ERROR is not None:
        failures.append(f"PySide2 Qt Widgets import failed: {QT_IMPORT_ERROR}")

    path_value = build_path()
    for command in REQUIRED_COMMANDS:
        if find_executable(command, path_value) is None:
            failures.append(f"Missing command: {command}")

    desktop_candidates = [
        DESKTOP_ENTRY,
        DEV_ROOT / "apps" / "crixa-welcome.desktop" if DEV_ROOT else None,
    ]
    if not any(candidate and candidate.exists() for candidate in desktop_candidates):
        failures.append("Missing crixa-welcome.desktop")

    try:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        probe = STATE_DIR / ".self-test"
        probe.write_text("ok\n", encoding="utf-8")
        probe.unlink()
    except Exception as exc:
        failures.append(f"State directory is not writable: {exc}")

    if failures:
        print("CRIXA_WELCOME_SELF_TEST_FAIL")
        for failure in failures:
            print(f"- {failure}")
        return 1

    qt_version = getattr(QtCore, "qVersion", lambda: "unknown")() if QtCore is not None else "missing"
    print("CRIXA_WELCOME_SELF_TEST_OK")
    print(f"Qt binding: PySide2 / Qt {qt_version}")
    print(f"Commands checked: {len(REQUIRED_COMMANDS)}")
    print(f"State marker: {SEEN_MARKER}")
    return 0


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=APP_NAME)
    parser.add_argument("--self-test", action="store_true", help="validate runtime dependencies")
    parser.add_argument("--force", action="store_true", help="open even when the first-run marker exists")
    parser.add_argument("--mark-seen", action="store_true", help="mark Welcome as seen and exit")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(list(argv if argv is not None else sys.argv[1:]))
    if args.self_test:
        return self_test()
    if args.mark_seen:
        write_seen_marker()
        return 0
    if not args.force and state_is_seen():
        return 0

    if QT_IMPORT_ERROR is not None or QtWidgets is None:
        print(f"{APP_NAME} requires python3-pyside2.qtwidgets: {QT_IMPORT_ERROR}", file=sys.stderr)
        return 127

    QtWidgets.QApplication.setAttribute(QtCore.Qt.AA_UseHighDpiPixmaps, True)
    app = QtWidgets.QApplication(sys.argv)
    QtGui.QIcon.setThemeName(os.environ.get("CRIXA_ICON_THEME", "CRIXA-Depth"))
    first_run = not args.force
    if first_run:
        write_seen_marker()
    window = WelcomeHub(first_run=first_run)
    window.show()
    window.raise_()
    window.activateWindow()
    return app.exec_()


if __name__ == "__main__":
    sys.exit(main())
