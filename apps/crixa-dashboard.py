#!/usr/bin/env python3
from __future__ import annotations

import argparse
import configparser
import json
import os
import shlex
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

try:
    from PySide2 import QtCore, QtGui, QtWidgets

    QT_IMPORT_ERROR: Exception | None = None
except Exception as exc:  # pragma: no cover - exercised by runtime fallback.
    QtCore = None
    QtGui = None
    QtWidgets = None
    QT_IMPORT_ERROR = exc


APP_NAME = "Orbit"
RECENT_LIMIT = 12
RECENT_PATH = (
    Path(os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local" / "share")))
    / "crixa"
    / "orbit"
    / "recent.json"
)

DEV_ROOT = Path(__file__).resolve().parents[1] if Path(__file__).resolve().parent.name == "apps" else None

PINNED_IDS = [
    "crixa-welcome.desktop",
    "crixa-browser.desktop",
    "crixa-files.desktop",
    "crixa-terminal.desktop",
    "crixa-store.desktop",
    "crixa-settings.desktop",
    "crixa-task-manager.desktop",
    "crixa-updater.desktop",
    "crixa-wallpapers.desktop",
]


@dataclass(slots=True)
class DesktopApp:
    desktop_id: str
    name: str
    comment: str
    exec_line: str
    icon: str
    categories: tuple[str, ...]
    keywords: tuple[str, ...]
    path: Path
    try_exec: str


@dataclass(frozen=True, slots=True)
class ActionSpec:
    action_id: str
    title: str
    subtitle: str
    command: tuple[str, ...]
    icon: str
    group: str


@dataclass(frozen=True, slots=True)
class CommandItem:
    item_id: str
    title: str
    subtitle: str
    icon: str
    kind: str
    app: DesktopApp | None = None
    command: tuple[str, ...] = ()


ACTION_SPECS = [
    ActionSpec("bridge", "Bridge", "System controls, appearance, and hardware", ("crixa-settings",), "preferences-system", "System"),
    ActionSpec("foundry", "Foundry", "Install and manage CRIXA apps", ("crixa-store",), "system-software-install", "System"),
    ActionSpec("pulse", "Pulse", "Processes, services, and live system load", ("crixa-task-manager",), "utilities-system-monitor", "System"),
    ActionSpec("transit", "Transit", "Updates, tracks, and rollback snapshots", ("crixa-updater",), "system-software-update", "System"),
    ActionSpec(
        "backdrop",
        "Backdrop",
        "Browse the installed wallpaper collection",
        ("crixa-files", "/usr/share/backgrounds/crixa"),
        "preferences-desktop-wallpaper",
        "System",
    ),
    ActionSpec("lock", "Lock", "Lock this session", ("loginctl", "lock-session"), "system-lock-screen", "Power"),
    ActionSpec("sleep", "Sleep", "Suspend this system", ("systemctl", "suspend"), "system-suspend", "Power"),
    ActionSpec("restart", "Restart", "Reboot now", ("systemctl", "reboot"), "system-reboot", "Power"),
    ActionSpec("poweroff", "Power Off", "Shut down this system", ("systemctl", "poweroff"), "system-shutdown", "Power"),
]


def bool_value(raw: str) -> bool:
    return raw.strip().lower() in {"1", "true", "yes"}


def split_desktop_list(raw: str) -> tuple[str, ...]:
    return tuple(part.strip() for part in raw.split(";") if part.strip())


def build_path(extra_bin_dirs: list[Path] | None = None) -> str:
    entries = [
        *(str(path) for path in extra_bin_dirs or []),
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
            seen.add(entry)
            deduped.append(entry)
    return os.pathsep.join(deduped)


def find_executable(program: str, path_value: str | None = None) -> str | None:
    if not program:
        return None
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
    return resolve_dev_command(program)


def resolve_dev_command(program: str) -> str | None:
    if DEV_ROOT is None or "/" in program:
        return None
    for suffix in ("", ".sh", ".py"):
        candidate = DEV_ROOT / "apps" / f"{program}{suffix}"
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)
    return None


def desktop_dirs(explicit_dirs: list[Path] | None = None) -> list[Path]:
    if explicit_dirs:
        return [path for path in explicit_dirs if path.exists()]

    env_dirs = os.environ.get("ORBIT_DESKTOP_DIRS")
    if env_dirs:
        return [Path(part) for part in env_dirs.split(os.pathsep) if part and Path(part).exists()]

    dirs: list[Path] = []
    if DEV_ROOT is not None:
        dirs.append(DEV_ROOT / "apps")

    data_home = Path(os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local" / "share")))
    dirs.append(data_home / "applications")

    data_dirs = os.environ.get("XDG_DATA_DIRS", "/usr/local/share:/usr/share")
    for raw in data_dirs.split(":"):
        if raw:
            dirs.append(Path(raw) / "applications")

    deduped: list[Path] = []
    seen: set[Path] = set()
    for path in dirs:
        resolved = path.expanduser()
        if resolved.exists() and resolved not in seen:
            seen.add(resolved)
            deduped.append(resolved)
    return deduped


def try_exec_available(raw: str, path_value: str) -> bool:
    if not raw.strip():
        return True
    try:
        executable = shlex.split(raw)[0]
    except ValueError:
        executable = raw.split()[0] if raw.split() else ""
    return find_executable(executable, path_value) is not None


def load_desktop_file(path: Path, path_value: str) -> DesktopApp | None:
    parser = configparser.ConfigParser(interpolation=None, strict=False)
    parser.optionxform = str
    try:
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            parser.read_file(handle)
    except Exception:
        return None

    if "Desktop Entry" not in parser:
        return None

    entry = parser["Desktop Entry"]
    if entry.get("Type", "").strip() != "Application":
        return None
    if bool_value(entry.get("Hidden", "false")):
        return None
    if bool_value(entry.get("NoDisplay", "false")):
        return None

    name = entry.get("Name", "").strip()
    exec_line = entry.get("Exec", "").strip()
    if not name or not exec_line:
        return None

    try_exec = entry.get("TryExec", "").strip()
    if try_exec and not try_exec_available(try_exec, path_value):
        return None

    return DesktopApp(
        desktop_id=path.name,
        name=name,
        comment=entry.get("Comment", "").strip() or entry.get("GenericName", "").strip(),
        exec_line=exec_line,
        icon=entry.get("Icon", "").strip(),
        categories=split_desktop_list(entry.get("Categories", "")),
        keywords=split_desktop_list(entry.get("Keywords", "")),
        path=path,
        try_exec=try_exec,
    )


def load_apps(explicit_dirs: list[Path] | None = None, path_value: str | None = None) -> list[DesktopApp]:
    resolved_path = path_value or build_path()
    discovered: dict[str, DesktopApp] = {}
    for directory in desktop_dirs(explicit_dirs):
        for path in sorted(directory.glob("*.desktop")):
            if path.name in discovered:
                continue
            app = load_desktop_file(path, resolved_path)
            if app is not None:
                discovered[app.desktop_id] = app
    return sorted(discovered.values(), key=lambda app: app.name.lower())


def command_for_desktop_exec(exec_line: str) -> list[str]:
    command: list[str] = []
    try:
        tokens = shlex.split(exec_line)
    except ValueError:
        return command

    field_codes = {"%f", "%F", "%u", "%U", "%d", "%D", "%n", "%N", "%i", "%c", "%k", "%v", "%m"}
    for token in tokens:
        if token in field_codes:
            continue
        cleaned = token.replace("%%", "\0")
        for code in field_codes:
            cleaned = cleaned.replace(code, "")
        cleaned = cleaned.replace("\0", "%").strip()
        if cleaned:
            command.append(cleaned)
    return command


def read_recent(path: Path = RECENT_PATH) -> list[str]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []

    ids: list[str] = []
    if isinstance(raw, list):
        for item in raw:
            if isinstance(item, str):
                ids.append(item)
            elif isinstance(item, dict) and isinstance(item.get("desktop_id"), str):
                ids.append(item["desktop_id"])
    elif isinstance(raw, dict) and isinstance(raw.get("items"), list):
        for item in raw["items"]:
            if isinstance(item, dict) and isinstance(item.get("desktop_id"), str):
                ids.append(item["desktop_id"])
    return ids[:RECENT_LIMIT]


def write_recent(desktop_ids: list[str], path: Path = RECENT_PATH) -> None:
    deduped: list[str] = []
    for desktop_id in desktop_ids:
        if desktop_id and desktop_id not in deduped:
            deduped.append(desktop_id)
    payload = {
        "version": 1,
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "items": [{"desktop_id": desktop_id} for desktop_id in deduped[:RECENT_LIMIT]],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def app_to_item(app: DesktopApp) -> CommandItem:
    return CommandItem(
        item_id=f"app:{app.desktop_id}",
        title=app.name,
        subtitle=app.comment or "Launch application",
        icon=app.icon or "application-x-executable",
        kind="app",
        app=app,
    )


def action_to_item(action: ActionSpec) -> CommandItem:
    return CommandItem(
        item_id=f"action:{action.action_id}",
        title=action.title,
        subtitle=action.subtitle,
        icon=action.icon,
        kind="action",
        command=action.command,
    )


def app_search_score(app: DesktopApp, query: str) -> int | None:
    haystacks = [
        app.name.lower(),
        app.comment.lower(),
        app.desktop_id.lower(),
        " ".join(app.categories).lower(),
        " ".join(app.keywords).lower(),
    ]
    if app.name.lower().startswith(query):
        return 0
    if any(part.startswith(query) for part in app.name.lower().split()):
        return 1
    for index, haystack in enumerate(haystacks):
        if query in haystack:
            return 2 + index
    return None


def item_search_score(item: CommandItem, query: str) -> int | None:
    title = item.title.lower()
    subtitle = item.subtitle.lower()
    if title.startswith(query):
        return 0
    if any(part.startswith(query) for part in title.split()):
        return 1
    if query in title:
        return 2
    if query in subtitle:
        return 3
    return None


def run_launch_tool(command: list[str], env: dict[str, str], timeout: int = 6) -> tuple[bool, str]:
    try:
        result = subprocess.run(command, env=env, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return False, f"{command[0]} timed out"
    except Exception as exc:
        return False, str(exc)

    if result.returncode == 0:
        return True, ""
    detail = (result.stderr or result.stdout or "").strip()
    if detail:
        return False, detail.splitlines()[-1]
    return False, f"{command[0]} exited with status {result.returncode}"


def direct_spawn(command: tuple[str, ...] | list[str], env: dict[str, str]) -> tuple[bool, str]:
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
        else:
            resolved[0] = found

    try:
        subprocess.Popen(resolved, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    except Exception as exc:
        return False, f"Could not launch {Path(resolved[0]).name}: {exc}"
    return True, ""


def launch_desktop_app(app: DesktopApp, env: dict[str, str]) -> tuple[bool, str, str]:
    errors: list[str] = []

    gio = find_executable("gio", env.get("PATH"))
    if gio and app.path.exists():
        ok, message = run_launch_tool([gio, "launch", str(app.path)], env)
        if ok:
            return True, "gio", ""
        errors.append(f"gio: {message}")

    gtk_launch = find_executable("gtk-launch", env.get("PATH"))
    if gtk_launch:
        ok, message = run_launch_tool([gtk_launch, app.desktop_id.removesuffix(".desktop")], env)
        if ok:
            return True, "gtk-launch", ""
        errors.append(f"gtk-launch: {message}")

    fallback = command_for_desktop_exec(app.exec_line)
    ok, message = direct_spawn(fallback, env)
    if ok:
        return True, "direct", ""
    errors.append(f"direct: {message}")

    return False, "", " | ".join(error for error in errors if error)


def launch_command(command: tuple[str, ...], env: dict[str, str]) -> tuple[bool, str]:
    ok, message = direct_spawn(command, env)
    if ok:
        return True, ""
    return False, message


if QtWidgets is not None:

    class SearchLineEdit(QtWidgets.QLineEdit):
        moveRequested = QtCore.Signal(int)
        launchRequested = QtCore.Signal()
        escapePressed = QtCore.Signal()

        def keyPressEvent(self, event: QtGui.QKeyEvent) -> None:
            if event.key() == QtCore.Qt.Key_Down:
                self.moveRequested.emit(1)
                event.accept()
                return
            if event.key() == QtCore.Qt.Key_Up:
                self.moveRequested.emit(-1)
                event.accept()
                return
            if event.key() in (QtCore.Qt.Key_Return, QtCore.Qt.Key_Enter):
                self.launchRequested.emit()
                event.accept()
                return
            if event.key() == QtCore.Qt.Key_Escape:
                self.escapePressed.emit()
                event.accept()
                return
            super().keyPressEvent(event)


    class CommandCard(QtWidgets.QFrame):
        clicked = QtCore.Signal(object)

        def __init__(self, item: CommandItem, parent: QtWidgets.QWidget | None = None) -> None:
            super().__init__(parent)
            self.item = item
            self.setObjectName("CommandCard")
            self.setCursor(QtCore.Qt.PointingHandCursor)
            self.setMinimumHeight(74)
            self.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)

            layout = QtWidgets.QHBoxLayout(self)
            layout.setContentsMargins(14, 12, 14, 12)
            layout.setSpacing(12)

            icon_label = QtWidgets.QLabel()
            icon = icon_for_name(item.icon)
            icon_label.setPixmap(icon.pixmap(28, 28))
            icon_label.setFixedSize(32, 32)
            icon_label.setAlignment(QtCore.Qt.AlignCenter)
            layout.addWidget(icon_label)

            text_layout = QtWidgets.QVBoxLayout()
            text_layout.setSpacing(2)
            title = QtWidgets.QLabel(item.title)
            title.setObjectName("CardTitle")
            subtitle = QtWidgets.QLabel(item.subtitle)
            subtitle.setObjectName("CardSubtitle")
            subtitle.setWordWrap(True)
            text_layout.addWidget(title)
            text_layout.addWidget(subtitle)
            layout.addLayout(text_layout, 1)

        def mouseReleaseEvent(self, event: QtGui.QMouseEvent) -> None:
            if event.button() == QtCore.Qt.LeftButton and self.rect().contains(event.pos()):
                self.clicked.emit(self.item)
            super().mouseReleaseEvent(event)


    class OrbitDashboard(QtWidgets.QWidget):
        def __init__(self) -> None:
            super().__init__()
            self.setWindowTitle(APP_NAME)
            self.setWindowFlags(QtCore.Qt.Window | QtCore.Qt.FramelessWindowHint)
            self.setAttribute(QtCore.Qt.WA_TranslucentBackground, True)

            self.apps = load_apps()
            self.app_map = {app.desktop_id: app for app in self.apps}
            self.recent_ids = read_recent()
            self.filtered_items: list[CommandItem] = []
            self.drag_position: QtCore.QPoint | None = None
            self.env = os.environ.copy()
            self.env["PATH"] = build_path()

            self.action_items = [action_to_item(action) for action in ACTION_SPECS]
            self._build_ui()
            self._position_window()
            self.refresh()
            self.search.setFocus(QtCore.Qt.OtherFocusReason)

        def _build_ui(self) -> None:
            outer = QtWidgets.QVBoxLayout(self)
            outer.setContentsMargins(0, 0, 0, 0)

            self.shell = QtWidgets.QFrame()
            self.shell.setObjectName("OrbitShell")
            outer.addWidget(self.shell)

            layout = QtWidgets.QVBoxLayout(self.shell)
            layout.setContentsMargins(18, 16, 18, 18)
            layout.setSpacing(14)

            self.header = QtWidgets.QFrame()
            self.header.setObjectName("Header")
            header_layout = QtWidgets.QHBoxLayout(self.header)
            header_layout.setContentsMargins(16, 14, 12, 14)
            header_layout.setSpacing(16)

            brand_layout = QtWidgets.QVBoxLayout()
            brand_layout.setSpacing(1)
            title = QtWidgets.QLabel("Orbit")
            title.setObjectName("Title")
            subtitle = QtWidgets.QLabel("Command Deck")
            subtitle.setObjectName("HeaderSubtitle")
            brand_layout.addWidget(title)
            brand_layout.addWidget(subtitle)
            header_layout.addLayout(brand_layout)

            self.search = SearchLineEdit()
            self.search.setObjectName("Search")
            self.search.setPlaceholderText("Search apps and system actions")
            self.search.textChanged.connect(self.refresh)
            self.search.moveRequested.connect(self.move_selection)
            self.search.launchRequested.connect(self.launch_selected)
            self.search.escapePressed.connect(self.close)
            header_layout.addWidget(self.search, 1)

            self.clock = QtWidgets.QLabel()
            self.clock.setObjectName("Clock")
            self.clock.setAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
            header_layout.addWidget(self.clock)

            close_btn = QtWidgets.QPushButton("x")
            close_btn.setObjectName("CloseButton")
            close_btn.setFixedSize(32, 32)
            close_btn.clicked.connect(self.close)
            header_layout.addWidget(close_btn)
            layout.addWidget(self.header)

            body = QtWidgets.QHBoxLayout()
            body.setSpacing(14)
            layout.addLayout(body, 1)

            self.left_panel = QtWidgets.QFrame()
            self.left_panel.setObjectName("Panel")
            left_layout = QtWidgets.QVBoxLayout(self.left_panel)
            left_layout.setContentsMargins(14, 14, 14, 14)
            left_layout.setSpacing(12)

            self.card_scroll = QtWidgets.QScrollArea()
            self.card_scroll.setObjectName("CardScroll")
            self.card_scroll.setWidgetResizable(True)
            self.card_scroll.setFrameShape(QtWidgets.QFrame.NoFrame)
            self.card_host = QtWidgets.QWidget()
            self.card_layout = QtWidgets.QVBoxLayout(self.card_host)
            self.card_layout.setContentsMargins(0, 0, 0, 0)
            self.card_layout.setSpacing(10)
            self.card_scroll.setWidget(self.card_host)
            left_layout.addWidget(self.card_scroll)
            body.addWidget(self.left_panel, 5)

            self.right_panel = QtWidgets.QFrame()
            self.right_panel.setObjectName("Panel")
            right_layout = QtWidgets.QVBoxLayout(self.right_panel)
            right_layout.setContentsMargins(14, 14, 14, 14)
            right_layout.setSpacing(10)

            results_header = QtWidgets.QHBoxLayout()
            results_title = QtWidgets.QLabel("Results")
            results_title.setObjectName("SectionTitle")
            self.count_label = QtWidgets.QLabel()
            self.count_label.setObjectName("Muted")
            self.count_label.setAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
            results_header.addWidget(results_title)
            results_header.addWidget(self.count_label, 1)
            right_layout.addLayout(results_header)

            self.results = QtWidgets.QListWidget()
            self.results.setObjectName("Results")
            self.results.setAlternatingRowColors(False)
            self.results.itemActivated.connect(lambda _item: self.launch_selected())
            self.results.itemClicked.connect(lambda _item: self.search.setFocus(QtCore.Qt.OtherFocusReason))
            right_layout.addWidget(self.results, 1)

            self.status = QtWidgets.QLabel()
            self.status.setObjectName("Status")
            self.status.setWordWrap(True)
            right_layout.addWidget(self.status)
            body.addWidget(self.right_panel, 4)

            self.apply_style()

            self.timer = QtCore.QTimer(self)
            self.timer.timeout.connect(self.tick_clock)
            self.timer.start(1000)
            self.tick_clock()

        def apply_style(self) -> None:
            self.setStyleSheet(
                """
                QWidget {
                    color: #eef4f2;
                    font-family: "IBM Plex Sans", "DejaVu Sans", sans-serif;
                    font-size: 10pt;
                    letter-spacing: 0;
                }
                QFrame#OrbitShell {
                    background: #0e1117;
                    border: 1px solid #3a4652;
                    border-radius: 18px;
                }
                QFrame#Header, QFrame#Panel {
                    background: #171d24;
                    border: 1px solid #2f3944;
                    border-radius: 12px;
                }
                QLabel#Title {
                    font-size: 24pt;
                    font-weight: 700;
                    color: #ffffff;
                }
                QLabel#HeaderSubtitle, QLabel#Muted, QLabel#Status {
                    color: #9ba8a7;
                }
                QLabel#Clock {
                    color: #d7eeea;
                    font-size: 12pt;
                    font-weight: 700;
                }
                QLabel#SectionTitle {
                    color: #f5fbf9;
                    font-size: 12pt;
                    font-weight: 700;
                }
                QLineEdit#Search {
                    background: #0b0f14;
                    color: #f5fbf9;
                    border: 1px solid #40505a;
                    border-radius: 10px;
                    padding: 12px 14px;
                    selection-background-color: #247f78;
                    font-size: 13pt;
                }
                QLineEdit#Search:focus {
                    border: 1px solid #35c9ba;
                }
                QPushButton#CloseButton {
                    background: #222b33;
                    border: 1px solid #394650;
                    border-radius: 16px;
                    color: #cbd6d3;
                    font-weight: 700;
                }
                QPushButton#CloseButton:hover {
                    background: #32404a;
                    color: #ffffff;
                }
                QScrollArea#CardScroll {
                    background: transparent;
                    border: none;
                }
                QFrame#CommandCard {
                    background: #202832;
                    border: 1px solid #34414a;
                    border-radius: 10px;
                }
                QFrame#CommandCard:hover {
                    background: #263340;
                    border: 1px solid #35c9ba;
                }
                QLabel#CardTitle {
                    color: #f6fbf9;
                    font-size: 11pt;
                    font-weight: 700;
                }
                QLabel#CardSubtitle {
                    color: #a5b1af;
                    font-size: 9pt;
                }
                QListWidget#Results {
                    background: #0b0f14;
                    border: 1px solid #2f3944;
                    border-radius: 10px;
                    outline: 0;
                    padding: 6px;
                }
                QListWidget#Results::item {
                    border-radius: 8px;
                    padding: 10px;
                    margin: 2px;
                }
                QListWidget#Results::item:selected {
                    background: #1d706a;
                    color: #ffffff;
                }
                QScrollBar:vertical {
                    background: transparent;
                    width: 10px;
                }
                QScrollBar::handle:vertical {
                    background: #374650;
                    border-radius: 5px;
                    min-height: 24px;
                }
                QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                    height: 0;
                }
                """
            )

        def _position_window(self) -> None:
            screen = QtWidgets.QApplication.primaryScreen()
            available = screen.availableGeometry() if screen else QtCore.QRect(0, 0, 1280, 720)
            width = min(1180, max(800, int(available.width() * 0.78)))
            height = min(760, max(560, int(available.height() * 0.78)))
            x = available.x() + max(12, (available.width() - width) // 2)
            y = available.y() + max(12, (available.height() - height) // 2)
            self.setGeometry(x, y, width, height)

        def tick_clock(self) -> None:
            self.clock.setText(datetime.now().strftime("%H:%M"))

        def pinned_items(self) -> list[CommandItem]:
            return [app_to_item(self.app_map[desktop_id]) for desktop_id in PINNED_IDS if desktop_id in self.app_map]

        def recent_items(self) -> list[CommandItem]:
            items: list[CommandItem] = []
            for desktop_id in self.recent_ids:
                app = self.app_map.get(desktop_id)
                if app is not None and desktop_id not in PINNED_IDS:
                    items.append(app_to_item(app))
            return items[:RECENT_LIMIT]

        def default_items(self) -> list[CommandItem]:
            items = self.pinned_items()
            seen = {item.item_id for item in items}
            for item in self.recent_items():
                if item.item_id not in seen:
                    seen.add(item.item_id)
                    items.append(item)
            for app in self.apps:
                item = app_to_item(app)
                if item.item_id not in seen:
                    seen.add(item.item_id)
                    items.append(item)
                if len(items) >= 24:
                    break
            return items

        def search_items(self, query: str) -> list[CommandItem]:
            scored: list[tuple[int, str, CommandItem]] = []
            for app in self.apps:
                score = app_search_score(app, query)
                if score is not None:
                    scored.append((score, app.name.lower(), app_to_item(app)))
            for item in self.action_items:
                score = item_search_score(item, query)
                if score is not None:
                    scored.append((score, item.title.lower(), item))
            return [item for _score, _name, item in sorted(scored)[:40]]

        def refresh(self) -> None:
            query = self.search.text().strip().lower()
            self.filtered_items = self.search_items(query) if query else self.default_items()
            self.refresh_cards(query)
            self.refresh_results(query)
            if query:
                self.status.setText(f"{len(self.filtered_items)} matches for '{query}'")
            else:
                self.status.setText(f"{len(self.apps)} applications indexed")

        def refresh_cards(self, query: str) -> None:
            while self.card_layout.count():
                item = self.card_layout.takeAt(0)
                widget = item.widget()
                if widget is not None:
                    widget.deleteLater()

            if query:
                self.add_card_section("Top Matches", self.filtered_items[:8])
            else:
                self.add_card_section("Pinned", self.pinned_items())
                recent = self.recent_items()
                if recent:
                    self.add_card_section("Recent", recent)
                self.add_card_section("System", [item for item in self.action_items if item.command and item.kind == "action" and item.item_id not in {"action:lock", "action:sleep", "action:restart", "action:poweroff"}])
                self.add_card_section("Power", [item for item in self.action_items if item.item_id in {"action:lock", "action:sleep", "action:restart", "action:poweroff"}])
            self.card_layout.addStretch(1)

        def add_card_section(self, title: str, items: list[CommandItem]) -> None:
            if not items:
                return
            label = QtWidgets.QLabel(title)
            label.setObjectName("SectionTitle")
            self.card_layout.addWidget(label)
            for item in items:
                card = CommandCard(item)
                card.clicked.connect(self.launch_item)
                self.card_layout.addWidget(card)

        def refresh_results(self, query: str) -> None:
            self.results.clear()
            for item in self.filtered_items:
                row = QtWidgets.QListWidgetItem()
                row.setText(f"{item.title}\n{item.subtitle}")
                row.setIcon(icon_for_name(item.icon))
                row.setSizeHint(QtCore.QSize(0, 56))
                row.setData(QtCore.Qt.UserRole, item)
                self.results.addItem(row)
            if self.results.count():
                self.results.setCurrentRow(0)
            label = "matches" if query else "ready"
            self.count_label.setText(f"{self.results.count()} {label}")

        def move_selection(self, delta: int) -> None:
            if self.results.count() == 0:
                return
            current = self.results.currentRow()
            if current < 0:
                current = 0
            next_row = max(0, min(self.results.count() - 1, current + delta))
            self.results.setCurrentRow(next_row)

        def launch_selected(self) -> None:
            row = self.results.currentRow()
            if row < 0 and self.results.count():
                row = 0
            if row < 0:
                return
            item = self.results.item(row).data(QtCore.Qt.UserRole)
            if isinstance(item, CommandItem):
                self.launch_item(item)

        def launch_item(self, item: CommandItem) -> None:
            if item.app is not None:
                ok, backend, message = launch_desktop_app(item.app, self.env)
                if ok:
                    self.record_recent(item.app.desktop_id)
                    self.status.setText(f"Launched {item.title} with {backend}")
                    self.close()
                    return
                self.status.setText(f"Could not launch {item.title}: {message}")
                self.search.setFocus(QtCore.Qt.OtherFocusReason)
                return

            ok, message = launch_command(item.command, self.env)
            if ok:
                self.status.setText(f"Launched {item.title}")
                self.close()
                return
            self.status.setText(f"Could not launch {item.title}: {message}")
            self.search.setFocus(QtCore.Qt.OtherFocusReason)

        def record_recent(self, desktop_id: str) -> None:
            self.recent_ids = [desktop_id, *[item for item in self.recent_ids if item != desktop_id]][:RECENT_LIMIT]
            try:
                write_recent(self.recent_ids)
            except Exception:
                pass

        def mousePressEvent(self, event: QtGui.QMouseEvent) -> None:
            if event.button() == QtCore.Qt.LeftButton and event.pos().y() <= 92:
                self.drag_position = event.globalPos() - self.frameGeometry().topLeft()
                event.accept()
                return
            super().mousePressEvent(event)

        def mouseMoveEvent(self, event: QtGui.QMouseEvent) -> None:
            if self.drag_position is not None and event.buttons() & QtCore.Qt.LeftButton:
                self.move(event.globalPos() - self.drag_position)
                event.accept()
                return
            super().mouseMoveEvent(event)

        def mouseReleaseEvent(self, event: QtGui.QMouseEvent) -> None:
            self.drag_position = None
            super().mouseReleaseEvent(event)


def icon_for_name(name: str):
    if QtGui is None:
        return None
    if name:
        icon_path = Path(name)
        if icon_path.is_absolute() and icon_path.exists():
            return QtGui.QIcon(str(icon_path))
        icon = QtGui.QIcon.fromTheme(name)
        if not icon.isNull():
            return icon
    fallback = QtGui.QIcon.fromTheme("application-x-executable")
    if not fallback.isNull():
        return fallback
    return QtWidgets.QApplication.style().standardIcon(QtWidgets.QStyle.SP_FileIcon)


def launch_backend_names(path_value: str) -> list[str]:
    names: list[str] = []
    if find_executable("gio", path_value):
        names.append("gio")
    if find_executable("gtk-launch", path_value):
        names.append("gtk-launch")
    names.append("direct-exec")
    return names


def self_test(args: argparse.Namespace) -> int:
    failures: list[str] = []
    if QT_IMPORT_ERROR is not None:
        failures.append(f"PySide2 Qt Widgets import failed: {QT_IMPORT_ERROR}")

    extra_bins = [Path(path) for path in args.bin_dir or []]
    path_value = build_path(extra_bins)
    explicit_dirs = [Path(path) for path in args.desktop_dir or []] or None
    apps = load_apps(explicit_dirs=explicit_dirs, path_value=path_value)
    app_map = {app.desktop_id: app for app in apps}

    if not apps:
        failures.append("No launchable desktop applications indexed")

    missing_pinned = [desktop_id for desktop_id in PINNED_IDS if desktop_id not in app_map]
    if missing_pinned:
        failures.append(f"Missing pinned applications: {', '.join(missing_pinned)}")

    backends = launch_backend_names(path_value)
    if not backends:
        failures.append("No launch backend discovered")

    if failures:
        print("ORBIT_SELF_TEST_FAIL")
        for failure in failures:
            print(f"- {failure}")
        return 1

    qt_version = getattr(QtCore, "qVersion", lambda: "unknown")() if QtCore is not None else "missing"
    print("ORBIT_SELF_TEST_OK")
    print(f"Qt binding: PySide2 / Qt {qt_version}")
    print(f"Applications indexed: {len(apps)}")
    print(f"Pinned present: {len(PINNED_IDS)}")
    print(f"Launch backends: {', '.join(backends)}")
    return 0


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Orbit Command Deck")
    parser.add_argument("--self-test", action="store_true", help="validate Orbit runtime dependencies and app indexing")
    parser.add_argument("--desktop-dir", action="append", help="desktop application directory to index during self-test")
    parser.add_argument("--bin-dir", action="append", help="binary directory to prepend during self-test")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(list(argv if argv is not None else sys.argv[1:]))
    if args.self_test:
        return self_test(args)

    if QT_IMPORT_ERROR is not None or QtWidgets is None:
        print(f"Orbit requires python3-pyside2.qtwidgets: {QT_IMPORT_ERROR}", file=sys.stderr)
        return 127

    QtWidgets.QApplication.setAttribute(QtCore.Qt.AA_UseHighDpiPixmaps, True)
    app = QtWidgets.QApplication(sys.argv)
    QtGui.QIcon.setThemeName(os.environ.get("CRIXA_ICON_THEME", "CRIXA-Depth"))
    window = OrbitDashboard()
    window.show()
    window.raise_()
    window.activateWindow()
    return app.exec_()


if __name__ == "__main__":
    sys.exit(main())
