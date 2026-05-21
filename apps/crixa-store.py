#!/usr/bin/env python3
from __future__ import annotations

import argparse
import html
import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

try:
    from PySide2 import QtCore, QtGui, QtWidgets

    QT_IMPORT_ERROR: Exception | None = None
except Exception as exc:  # pragma: no cover - exercised on minimal hosts
    QtCore = QtGui = QtWidgets = None  # type: ignore[assignment]
    QT_IMPORT_ERROR = exc


APP_NAME = "Foundry"
DEFAULT_BACKEND = "crixa-repo"
SYSTEM_BACKEND_DIR = Path("/usr/share/crixa-store/backends")
USER_BACKEND_DIRS = [
    Path.home() / ".local" / "share" / "crixa-store" / "backends",
    Path.home() / ".config" / "crixa-store" / "backends",
]
CONFIG_DIR = Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config"))) / "crixa-store"
CACHE_ROOT = Path(os.environ.get("XDG_CACHE_HOME", str(Path.home() / ".cache"))) / "crixa-store" / "repos"
OPERATIONS_DIR = Path(os.environ.get("XDG_STATE_HOME", str(Path.home() / ".local" / "state"))) / "crixa-store" / "operations"
SYSTEM_CATALOG_PATH = Path("/usr/share/crixa-store/catalog.json")

DEV_ROOT = Path(__file__).resolve().parents[1] if Path(__file__).resolve().parent.name == "apps" else None
DEV_BACKEND_DIR = DEV_ROOT / "store-backends" / "manifests" if DEV_ROOT else None
DEV_CATALOG_PATH = DEV_ROOT / "store-packages" / "catalog.json" if DEV_ROOT else None

ALL_CATEGORIES = "All"
INSTALLED_CATEGORY = "Installed"
UPDATES_CATEGORY = "Updates"


@dataclass(slots=True)
class Backend:
    backend_id: str
    name: str
    command: list[str]
    supports_upgrade: bool
    priority: int
    description: str
    manifest_path: Path


def load_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def discover_backend_manifests() -> list[Path]:
    paths: list[Path] = []
    for directory in [DEV_BACKEND_DIR, SYSTEM_BACKEND_DIR, *USER_BACKEND_DIRS]:
        if directory is None or not directory.is_dir():
            continue
        paths.extend(sorted(directory.glob("*.json")))
    deduped: dict[str, Path] = {}
    for path in paths:
        deduped[path.name] = path
    return list(deduped.values())


def resolve_backend_command(command: list[str]) -> list[str]:
    if not command:
        return []
    resolved = list(command)
    first = Path(resolved[0])
    if DEV_ROOT is not None and first.name:
        local_backend = DEV_ROOT / "store-backends" / first.name
        if local_backend.exists():
            resolved[0] = str(local_backend)
    return resolved


def load_backends() -> list[Backend]:
    backends: list[Backend] = []
    for manifest in discover_backend_manifests():
        data = load_json(manifest, {})
        if not isinstance(data, dict):
            continue
        backend_id = str(data.get("id", "")).strip()
        command = data.get("command", [])
        if isinstance(command, str):
            command = [command]
        if not backend_id or not isinstance(command, list):
            continue
        command = [str(item) for item in command if str(item).strip()]
        resolved = resolve_backend_command(command)
        if not resolved:
            continue
        backends.append(
            Backend(
                backend_id=backend_id,
                name=str(data.get("name", backend_id)),
                command=resolved,
                supports_upgrade=bool(data.get("supports_upgrade", False)),
                priority=int(data.get("priority", 50)),
                description=str(data.get("description", "")),
                manifest_path=manifest,
            )
        )
    backends.sort(key=lambda backend: (backend.priority, backend.name.lower()))
    return backends


def call_backend(backend: Backend, request: dict, timeout: int = 120) -> dict:
    command = list(backend.command)
    if command and command[0].endswith(".py"):
        command = [sys.executable, *command]
    try:
        result = subprocess.run(
            command,
            input=json.dumps(request),
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "backend timed out", "message": "backend timed out"}
    except FileNotFoundError as exc:
        return {"ok": False, "error": str(exc), "message": str(exc)}
    stdout = (result.stdout or "").strip()
    stderr = (result.stderr or "").strip()
    if not stdout:
        return {"ok": False, "error": stderr or "backend returned no response", "message": stderr or "backend returned no response"}
    try:
        payload = json.loads(stdout)
    except json.JSONDecodeError:
        return {"ok": False, "error": stdout.splitlines()[-1], "message": stdout.splitlines()[-1], "log": [stdout, stderr]}
    if result.returncode != 0 and payload.get("ok", True):
        payload["ok"] = False
        payload.setdefault("error", stderr or payload.get("message", "backend failed"))
    payload.setdefault("message", payload.get("error", "ok"))
    return payload


def ensure_app_shape(app: dict, source_id: str) -> dict:
    app_id = str(app.get("id", "")).strip()
    name = str(app.get("name", app_id or "Unnamed")).strip() or app_id or "Unnamed"
    lists = {}
    for key in ("features", "tags", "screenshots", "permissions", "release_notes", "install_scopes", "installed_scopes"):
        value = app.get(key, [])
        lists[key] = [str(item) for item in value] if isinstance(value, list) else []
    return {
        "id": app_id,
        "name": name,
        "version": str(app.get("version", "n/a")),
        "category": str(app.get("category", "General")),
        "summary": str(app.get("summary", "")),
        "description": str(app.get("description", "")),
        "features": lists["features"],
        "tags": lists["tags"],
        "entrypoint": str(app.get("entrypoint", "")),
        "size": str(app.get("size", "")),
        "installed": bool(app.get("installed", False)),
        "installed_scopes": lists["installed_scopes"],
        "source": str(app.get("source", app.get("source_id", source_id))),
        "source_id": str(app.get("source_id", app.get("source", source_id))),
        "source_name": str(app.get("source_name", source_id)),
        "backend": str(app.get("backend", source_id)),
        "publisher": str(app.get("publisher", "CRIXA Project")),
        "license": str(app.get("license", "")),
        "homepage": str(app.get("homepage", "")),
        "release_notes": lists["release_notes"],
        "permissions": lists["permissions"],
        "screenshots": lists["screenshots"],
        "hero_image": str(app.get("hero_image", "")),
        "install_scopes": lists["install_scopes"] or ["user"],
        "asset_base": str(app.get("asset_base", "")),
        "error": str(app.get("error", "")),
    }


def category_rank(name: str) -> tuple[int, str]:
    preferred = ["Productivity", "Creative", "Utilities", "Developer", "System", "Media", "Games", "General", "Source"]
    if name in preferred:
        return (preferred.index(name), name)
    return (len(preferred), name)


def self_test() -> int:
    failures: list[str] = []
    if QT_IMPORT_ERROR is not None:
        failures.append(f"PySide2 Qt Widgets import failed: {QT_IMPORT_ERROR}")

    backends = load_backends()
    if not backends:
        failures.append("No store backend manifests were discovered")
    default = next((backend for backend in backends if backend.backend_id == DEFAULT_BACKEND), backends[0] if backends else None)
    if default is None:
        failures.append("CRIXA backend is unavailable")
    else:
        payload = call_backend(default, {"action": "capabilities"}, timeout=20)
        if not payload.get("ok"):
            failures.append(f"Backend capabilities failed: {payload.get('error') or payload.get('message')}")
        else:
            required = {"list", "install", "remove", "launch", "sources", "add-source", "refresh-source"}
            caps = set(payload.get("capabilities", []))
            missing = sorted(required - caps)
            if missing:
                failures.append(f"Backend missing capabilities: {', '.join(missing)}")

    catalog_path = SYSTEM_CATALOG_PATH
    if not catalog_path.exists() and DEV_CATALOG_PATH is not None:
        catalog_path = DEV_CATALOG_PATH
    catalog = load_json(catalog_path, {})
    if not isinstance(catalog, dict) or not isinstance(catalog.get("apps", []), list):
        failures.append(f"Catalog is not readable: {catalog_path}")

    for path in (CONFIG_DIR, CACHE_ROOT, OPERATIONS_DIR):
        try:
            path.mkdir(parents=True, exist_ok=True)
            probe = path / ".self-test"
            probe.write_text("ok\n", encoding="utf-8")
            probe.unlink(missing_ok=True)
        except Exception as exc:
            failures.append(f"State path is not writable: {path} ({exc})")

    if failures:
        print("Foundry self-test failed:")
        for item in failures:
            print(f"- {item}")
        return 1

    qt_version = QtCore.qVersion() if QtCore is not None else "unavailable"
    print("Foundry self-test passed")
    print(f"Qt binding: PySide2 / Qt {qt_version}")
    print(f"Backends: {', '.join(backend.backend_id for backend in backends)}")
    print(f"Config: {CONFIG_DIR}")
    print(f"Cache: {CACHE_ROOT}")
    return 0


if QT_IMPORT_ERROR is None:

    class BackendJob(QtCore.QThread):
        finished_payload = QtCore.Signal(dict)

        def __init__(self, backend: Backend, request: dict, timeout: int = 180, parent=None) -> None:
            super().__init__(parent)
            self.backend = backend
            self.request = request
            self.timeout = timeout

        def run(self) -> None:
            self.finished_payload.emit(call_backend(self.backend, self.request, timeout=self.timeout))


    class AppCard(QtWidgets.QFrame):
        clicked = QtCore.Signal(dict)

        def __init__(self, app: dict, parent=None) -> None:
            super().__init__(parent)
            self.app = app
            self.setObjectName("AppCard")
            self.setCursor(QtCore.Qt.PointingHandCursor)
            self.setMinimumHeight(146)
            self.setMaximumHeight(170)
            self.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)

            layout = QtWidgets.QVBoxLayout(self)
            layout.setContentsMargins(14, 12, 14, 12)
            layout.setSpacing(7)

            top = QtWidgets.QHBoxLayout()
            icon = QtWidgets.QLabel()
            icon.setFixedSize(38, 38)
            icon.setObjectName("AppGlyph")
            icon_name = "emblem-system" if app.get("installed") else "applications-other"
            icon.setPixmap(QtGui.QIcon.fromTheme(icon_name).pixmap(24, 24))
            top.addWidget(icon)

            title_box = QtWidgets.QVBoxLayout()
            title = QtWidgets.QLabel(app.get("name", "Unnamed"))
            title.setObjectName("CardTitle")
            title.setWordWrap(False)
            source = QtWidgets.QLabel(f"{app.get('category', 'General')} - {app.get('source_name', app.get('source_id', 'Source'))}")
            source.setObjectName("CardMeta")
            title_box.addWidget(title)
            title_box.addWidget(source)
            top.addLayout(title_box, 1)
            status = QtWidgets.QLabel("Installed" if app.get("installed") else str(app.get("version", "")))
            status.setObjectName("InstalledBadge" if app.get("installed") else "VersionBadge")
            top.addWidget(status, 0, QtCore.Qt.AlignTop)
            layout.addLayout(top)

            summary = QtWidgets.QLabel(app.get("summary") or app.get("description") or "No summary available.")
            summary.setObjectName("CardSummary")
            summary.setWordWrap(True)
            summary.setMaximumHeight(46)
            layout.addWidget(summary)

            tags = app.get("tags", [])[:3]
            if tags:
                tag_line = QtWidgets.QLabel("  ".join(tags))
                tag_line.setObjectName("CardTags")
                tag_line.setWordWrap(False)
                layout.addWidget(tag_line)
            layout.addStretch(1)

        def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt naming
            if event.button() == QtCore.Qt.LeftButton:
                self.clicked.emit(self.app)
            super().mousePressEvent(event)


    class StoreWindow(QtWidgets.QMainWindow):
        def __init__(self) -> None:
            super().__init__()
            self.setWindowTitle(APP_NAME)
            self.resize(1240, 780)
            self.setMinimumSize(1040, 660)

            self.backends = load_backends()
            self.backend_map = {backend.backend_id: backend for backend in self.backends}
            self.current_backend_id = DEFAULT_BACKEND if DEFAULT_BACKEND in self.backend_map else (self.backends[0].backend_id if self.backends else "")
            self.sources: list[dict] = []
            self.apps: list[dict] = []
            self.filtered_apps: list[dict] = []
            self.selected_category = ALL_CATEGORIES
            self.selected_app: dict | None = None
            self.active_job: BackendJob | None = None

            self.build_ui()
            self.apply_style()
            self.populate_backends()
            if not self.backends:
                self.set_status("No store backend manifests found.", error=True)
            else:
                QtCore.QTimer.singleShot(80, self.reload_everything)

        def current_backend(self) -> Backend | None:
            return self.backend_map.get(self.current_backend_id)

        def build_ui(self) -> None:
            root = QtWidgets.QWidget()
            root.setObjectName("Root")
            self.setCentralWidget(root)
            shell = QtWidgets.QHBoxLayout(root)
            shell.setContentsMargins(0, 0, 0, 0)
            shell.setSpacing(0)

            rail = QtWidgets.QFrame()
            rail.setObjectName("Rail")
            rail.setFixedWidth(248)
            rail_layout = QtWidgets.QVBoxLayout(rail)
            rail_layout.setContentsMargins(18, 22, 16, 18)
            rail_layout.setSpacing(12)
            shell.addWidget(rail)

            title = QtWidgets.QLabel("Foundry")
            title.setObjectName("RailTitle")
            subtitle = QtWidgets.QLabel("Software Center")
            subtitle.setObjectName("RailSubtitle")
            rail_layout.addWidget(title)
            rail_layout.addWidget(subtitle)

            self.backend_combo = QtWidgets.QComboBox()
            self.backend_combo.setObjectName("QuietCombo")
            self.backend_combo.currentIndexChanged.connect(self.on_backend_changed)
            rail_layout.addWidget(self.backend_combo)

            self.source_combo = QtWidgets.QComboBox()
            self.source_combo.setObjectName("QuietCombo")
            self.source_combo.currentIndexChanged.connect(self.on_source_changed)
            rail_layout.addWidget(self.source_combo)

            source_buttons = QtWidgets.QHBoxLayout()
            self.add_source_btn = QtWidgets.QToolButton()
            self.add_source_btn.setIcon(QtGui.QIcon.fromTheme("list-add"))
            self.add_source_btn.setToolTip("Add signed repository source")
            self.add_source_btn.clicked.connect(self.add_source)
            self.remove_source_btn = QtWidgets.QToolButton()
            self.remove_source_btn.setIcon(QtGui.QIcon.fromTheme("list-remove"))
            self.remove_source_btn.setToolTip("Remove selected repository source")
            self.remove_source_btn.clicked.connect(self.remove_source)
            self.refresh_source_btn = QtWidgets.QToolButton()
            self.refresh_source_btn.setIcon(QtGui.QIcon.fromTheme("view-refresh"))
            self.refresh_source_btn.setToolTip("Refresh selected source")
            self.refresh_source_btn.clicked.connect(self.refresh_source)
            source_buttons.addWidget(self.add_source_btn)
            source_buttons.addWidget(self.remove_source_btn)
            source_buttons.addWidget(self.refresh_source_btn)
            source_buttons.addStretch(1)
            rail_layout.addLayout(source_buttons)

            label = QtWidgets.QLabel("Browse")
            label.setObjectName("RailSection")
            rail_layout.addWidget(label)

            self.category_layout = QtWidgets.QVBoxLayout()
            self.category_layout.setSpacing(7)
            rail_layout.addLayout(self.category_layout)
            rail_layout.addStretch(1)

            self.upgrade_btn = QtWidgets.QPushButton(QtGui.QIcon.fromTheme("system-software-update"), "Upgrade")
            self.upgrade_btn.clicked.connect(self.upgrade_apps)
            rail_layout.addWidget(self.upgrade_btn)

            main = QtWidgets.QFrame()
            main.setObjectName("Main")
            main_layout = QtWidgets.QVBoxLayout(main)
            main_layout.setContentsMargins(22, 20, 22, 18)
            main_layout.setSpacing(14)
            shell.addWidget(main, 1)

            header = QtWidgets.QHBoxLayout()
            heading_box = QtWidgets.QVBoxLayout()
            heading = QtWidgets.QLabel("Software")
            heading.setObjectName("PageTitle")
            self.hero_copy = QtWidgets.QLabel("Featured CRIXA apps, remote-ready sources, and scoped installs.")
            self.hero_copy.setObjectName("PageSubtitle")
            heading_box.addWidget(heading)
            heading_box.addWidget(self.hero_copy)
            header.addLayout(heading_box, 1)
            self.search = QtWidgets.QLineEdit()
            self.search.setObjectName("SearchBox")
            self.search.setPlaceholderText("Search apps, publishers, permissions...")
            self.search.textChanged.connect(self.apply_filters)
            header.addWidget(self.search, 0)
            main_layout.addLayout(header)

            self.hero = QtWidgets.QFrame()
            self.hero.setObjectName("Hero")
            hero_layout = QtWidgets.QHBoxLayout(self.hero)
            hero_layout.setContentsMargins(18, 16, 18, 16)
            hero_text = QtWidgets.QVBoxLayout()
            self.hero_title = QtWidgets.QLabel("Curated CRIXA Catalog")
            self.hero_title.setObjectName("HeroTitle")
            self.hero_body = QtWidgets.QLabel("Install user-local apps by default, switch to system scope when you mean it, and keep signed sources visible.")
            self.hero_body.setObjectName("HeroBody")
            self.hero_body.setWordWrap(True)
            hero_text.addWidget(self.hero_title)
            hero_text.addWidget(self.hero_body)
            hero_layout.addLayout(hero_text, 1)
            self.stats_label = QtWidgets.QLabel("0 apps")
            self.stats_label.setObjectName("HeroStat")
            hero_layout.addWidget(self.stats_label)
            main_layout.addWidget(self.hero)

            content = QtWidgets.QHBoxLayout()
            content.setSpacing(14)
            main_layout.addLayout(content, 1)

            self.scroll = QtWidgets.QScrollArea()
            self.scroll.setObjectName("CatalogScroll")
            self.scroll.setWidgetResizable(True)
            self.cards_host = QtWidgets.QWidget()
            self.cards_layout = QtWidgets.QGridLayout(self.cards_host)
            self.cards_layout.setContentsMargins(0, 0, 8, 0)
            self.cards_layout.setHorizontalSpacing(12)
            self.cards_layout.setVerticalSpacing(12)
            self.scroll.setWidget(self.cards_host)
            content.addWidget(self.scroll, 1)

            detail = QtWidgets.QFrame()
            detail.setObjectName("Detail")
            detail.setFixedWidth(372)
            detail_layout = QtWidgets.QVBoxLayout(detail)
            detail_layout.setContentsMargins(16, 16, 16, 16)
            detail_layout.setSpacing(10)
            content.addWidget(detail)

            self.preview = QtWidgets.QLabel()
            self.preview.setObjectName("Preview")
            self.preview.setFixedHeight(150)
            self.preview.setAlignment(QtCore.Qt.AlignCenter)
            self.preview.setText("Select an app")
            detail_layout.addWidget(self.preview)

            self.detail_title = QtWidgets.QLabel("No app selected")
            self.detail_title.setObjectName("DetailTitle")
            self.detail_title.setWordWrap(True)
            detail_layout.addWidget(self.detail_title)
            self.detail_meta = QtWidgets.QLabel("")
            self.detail_meta.setObjectName("DetailMeta")
            self.detail_meta.setWordWrap(True)
            detail_layout.addWidget(self.detail_meta)
            self.detail_desc = QtWidgets.QTextBrowser()
            self.detail_desc.setObjectName("DetailText")
            self.detail_desc.setOpenExternalLinks(True)
            detail_layout.addWidget(self.detail_desc, 1)

            scope_row = QtWidgets.QHBoxLayout()
            scope_label = QtWidgets.QLabel("Install scope")
            scope_label.setObjectName("DetailMeta")
            self.scope_combo = QtWidgets.QComboBox()
            self.scope_combo.addItem("User", "user")
            self.scope_combo.addItem("System", "system")
            scope_row.addWidget(scope_label)
            scope_row.addWidget(self.scope_combo, 1)
            detail_layout.addLayout(scope_row)

            action_row = QtWidgets.QHBoxLayout()
            self.install_btn = QtWidgets.QPushButton(QtGui.QIcon.fromTheme("system-software-install"), "Install")
            self.install_btn.clicked.connect(self.install_selected)
            self.launch_btn = QtWidgets.QPushButton(QtGui.QIcon.fromTheme("media-playback-start"), "Launch")
            self.launch_btn.clicked.connect(self.launch_selected)
            self.remove_btn = QtWidgets.QPushButton(QtGui.QIcon.fromTheme("edit-delete"), "Remove")
            self.remove_btn.clicked.connect(self.remove_selected)
            action_row.addWidget(self.install_btn)
            action_row.addWidget(self.launch_btn)
            action_row.addWidget(self.remove_btn)
            detail_layout.addLayout(action_row)

            self.progress = QtWidgets.QProgressBar()
            self.progress.setRange(0, 100)
            self.progress.setValue(0)
            self.progress.setTextVisible(False)
            detail_layout.addWidget(self.progress)
            self.status = QtWidgets.QLabel("Opening Foundry...")
            self.status.setObjectName("Status")
            self.status.setWordWrap(True)
            detail_layout.addWidget(self.status)
            self.log = QtWidgets.QTextEdit()
            self.log.setObjectName("Log")
            self.log.setReadOnly(True)
            self.log.setFixedHeight(94)
            detail_layout.addWidget(self.log)

        def apply_style(self) -> None:
            self.setStyleSheet(
                """
                QWidget#Root { background: #101316; color: #edf5f2; font-family: "IBM Plex Sans", "Inter", "Helvetica", sans-serif; font-size: 10.5pt; }
                QFrame#Rail { background: #161b20; border-right: 1px solid #29323a; }
                QLabel#RailTitle { color: #f5fbf9; font-size: 24px; font-weight: 700; }
                QLabel#RailSubtitle, QLabel#PageSubtitle, QLabel#DetailMeta, QLabel#CardMeta { color: #8fa19e; }
                QLabel#RailSection { color: #c9d8d3; font-weight: 700; margin-top: 8px; }
                QFrame#Main { background: #101316; }
                QLabel#PageTitle { color: #f4fbf8; font-size: 26px; font-weight: 750; }
                QLineEdit#SearchBox, QComboBox#QuietCombo, QComboBox { background: #0b0e11; border: 1px solid #303a43; border-radius: 7px; padding: 8px 10px; color: #edf5f2; min-height: 22px; }
                QLineEdit#SearchBox:focus, QComboBox#QuietCombo:focus, QComboBox:focus { border-color: #34c6b6; }
                QFrame#Hero { background: #1b2428; border: 1px solid #30434a; border-radius: 8px; }
                QLabel#HeroTitle { color: #ffffff; font-size: 17px; font-weight: 750; }
                QLabel#HeroBody { color: #a9bab5; }
                QLabel#HeroStat { color: #f1bd58; font-weight: 700; font-size: 13px; padding-left: 18px; }
                QScrollArea#CatalogScroll { border: 0; background: transparent; }
                QFrame#AppCard { background: #182027; border: 1px solid #2c3842; border-radius: 8px; }
                QFrame#AppCard:hover { border-color: #39c7b7; background: #1b2730; }
                QLabel#AppGlyph { background: #0d1115; border: 1px solid #34424b; border-radius: 8px; qproperty-alignment: AlignCenter; }
                QLabel#CardTitle { color: #f5faf7; font-weight: 720; font-size: 13px; }
                QLabel#CardSummary { color: #bdcbc7; }
                QLabel#CardTags { color: #82d7ca; font-size: 9.5pt; }
                QLabel#InstalledBadge { color: #08100f; background: #42d6b7; border-radius: 7px; padding: 3px 8px; font-weight: 700; }
                QLabel#VersionBadge { color: #e8c16d; background: #302715; border-radius: 7px; padding: 3px 8px; font-weight: 700; }
                QFrame#Detail { background: #161d23; border-left: 1px solid #2a343c; }
                QLabel#Preview { background: #0b0e11; border: 1px solid #303a43; border-radius: 8px; color: #78908b; font-size: 15px; font-weight: 700; }
                QLabel#DetailTitle { color: #f4fbf8; font-size: 20px; font-weight: 760; }
                QTextBrowser#DetailText, QTextEdit#Log { background: #0d1115; border: 1px solid #303a43; border-radius: 8px; color: #d9e5e1; padding: 8px; }
                QTextEdit#Log { color: #9fb4ae; font-family: "IBM Plex Mono", monospace; font-size: 9pt; }
                QLabel#Status { color: #aec0ba; }
                QPushButton { background: #25313a; border: 1px solid #3a4852; border-radius: 7px; color: #f2fbf7; padding: 8px 10px; font-weight: 650; }
                QPushButton:hover { background: #2b3a44; border-color: #4f6570; }
                QPushButton:disabled { color: #62716d; background: #171c20; border-color: #252d33; }
                QToolButton { background: #202a32; border: 1px solid #33414b; border-radius: 7px; color: #eef6f3; padding: 7px; }
                QToolButton:hover { border-color: #39c7b7; }
                QProgressBar { background: #0d1115; border: 1px solid #303a43; border-radius: 4px; height: 7px; }
                QProgressBar::chunk { background: #34c6b6; border-radius: 4px; }
                """
            )

        def populate_backends(self) -> None:
            self.backend_combo.blockSignals(True)
            self.backend_combo.clear()
            for backend in self.backends:
                self.backend_combo.addItem(backend.name, backend.backend_id)
            index = self.backend_combo.findData(self.current_backend_id)
            if index >= 0:
                self.backend_combo.setCurrentIndex(index)
            self.backend_combo.blockSignals(False)

        def reload_everything(self) -> None:
            self.load_sources()
            self.load_apps()

        def on_backend_changed(self) -> None:
            backend_id = self.backend_combo.currentData()
            if backend_id:
                self.current_backend_id = str(backend_id)
                self.sources = []
                self.reload_everything()

        def selected_source_id(self) -> str:
            data = self.source_combo.currentData()
            return str(data or "all")

        def on_source_changed(self) -> None:
            self.load_apps()

        def backend_payload(self, request: dict, timeout: int = 120) -> dict:
            backend = self.current_backend()
            if backend is None:
                return {"ok": False, "message": "No backend selected", "error": "No backend selected"}
            return call_backend(backend, request, timeout=timeout)

        def load_sources(self) -> None:
            payload = self.backend_payload({"action": "sources"}, timeout=30)
            if payload.get("ok") and isinstance(payload.get("sources"), list):
                self.sources = [source for source in payload["sources"] if isinstance(source, dict)]
            else:
                backend = self.current_backend()
                self.sources = [{"id": backend.backend_id if backend else "source", "name": backend.name if backend else "Source", "builtin": True, "enabled": True}]
                if payload.get("error"):
                    self.set_status(str(payload.get("error")), error=True)
            current = self.selected_source_id()
            self.source_combo.blockSignals(True)
            self.source_combo.clear()
            self.source_combo.addItem("All Sources", "all")
            for source in self.sources:
                label = str(source.get("name", source.get("id", "Source")))
                status = str(source.get("status", ""))
                if status and status not in ("ready", "configured"):
                    label = f"{label} ({status})"
                self.source_combo.addItem(label, source.get("id", ""))
            index = self.source_combo.findData(current)
            self.source_combo.setCurrentIndex(index if index >= 0 else 0)
            self.source_combo.blockSignals(False)

        def load_apps(self) -> None:
            self.set_busy(True, "Refreshing catalog...")
            payload = self.backend_payload(
                {
                    "action": "list",
                    "query": self.search.text().strip(),
                    "limit": 500,
                    "source_id": self.selected_source_id(),
                },
                timeout=60,
            )
            self.set_busy(False)
            if not payload.get("ok"):
                self.apps = []
                self.render_cards()
                self.set_status(str(payload.get("error") or payload.get("message") or "Could not load apps"), error=True)
                return
            self.sources = [source for source in payload.get("sources", self.sources) if isinstance(source, dict)]
            self.apps = [ensure_app_shape(app, DEFAULT_BACKEND) for app in payload.get("apps", []) if isinstance(app, dict)]
            self.rebuild_categories()
            self.apply_filters()
            self.set_status("Catalog ready")

        def rebuild_categories(self) -> None:
            while self.category_layout.count():
                item = self.category_layout.takeAt(0)
                widget = item.widget()
                if widget:
                    widget.deleteLater()
            categories = sorted({app.get("category", "General") for app in self.apps}, key=category_rank)
            labels = [ALL_CATEGORIES, INSTALLED_CATEGORY, *categories]
            for label in labels:
                button = QtWidgets.QPushButton(label)
                button.setCheckable(True)
                button.setChecked(label == self.selected_category)
                button.clicked.connect(lambda _checked=False, value=label: self.select_category(value))
                self.category_layout.addWidget(button)

        def select_category(self, category: str) -> None:
            self.selected_category = category
            for index in range(self.category_layout.count()):
                widget = self.category_layout.itemAt(index).widget()
                if isinstance(widget, QtWidgets.QPushButton):
                    widget.setChecked(widget.text() == category)
            self.apply_filters()

        def apply_filters(self) -> None:
            query = self.search.text().strip().lower()
            filtered = []
            for app in self.apps:
                if self.selected_category == INSTALLED_CATEGORY and not app.get("installed"):
                    continue
                if self.selected_category not in (ALL_CATEGORIES, INSTALLED_CATEGORY) and app.get("category") != self.selected_category:
                    continue
                haystack = " ".join(
                    [
                        app.get("id", ""),
                        app.get("name", ""),
                        app.get("summary", ""),
                        app.get("description", ""),
                        app.get("publisher", ""),
                        " ".join(app.get("features", [])),
                        " ".join(app.get("tags", [])),
                        " ".join(app.get("permissions", [])),
                    ]
                ).lower()
                if query and query not in haystack:
                    continue
                filtered.append(app)
            self.filtered_apps = filtered
            self.render_cards()

        def render_cards(self) -> None:
            while self.cards_layout.count():
                item = self.cards_layout.takeAt(0)
                widget = item.widget()
                if widget:
                    widget.deleteLater()
            if not self.filtered_apps:
                empty = QtWidgets.QLabel("No apps match this view.")
                empty.setObjectName("PageSubtitle")
                self.cards_layout.addWidget(empty, 0, 0)
            columns = 2 if self.width() >= 1100 else 1
            for index, app in enumerate(self.filtered_apps):
                card = AppCard(app)
                card.clicked.connect(self.select_app)
                row, col = divmod(index, columns)
                self.cards_layout.addWidget(card, row, col)
            self.cards_layout.setRowStretch((len(self.filtered_apps) // max(columns, 1)) + 1, 1)
            self.stats_label.setText(f"{len(self.filtered_apps)} apps")
            if self.selected_app:
                matched = next((app for app in self.apps if app.get("id") == self.selected_app.get("id") and app.get("source_id") == self.selected_app.get("source_id")), None)
                self.select_app(matched or self.selected_app)

        def resizeEvent(self, event) -> None:  # noqa: N802
            super().resizeEvent(event)
            QtCore.QTimer.singleShot(0, self.render_cards)

        def select_app(self, app: dict) -> None:
            self.selected_app = app
            self.detail_title.setText(app.get("name", "Unnamed"))
            installed_scopes = app.get("installed_scopes", [])
            installed_text = f"Installed: {', '.join(installed_scopes)}" if installed_scopes else "Not installed"
            meta = f"{app.get('publisher', 'Publisher')} - {app.get('category', 'General')} - {app.get('version', '')} - {installed_text}"
            self.detail_meta.setText(meta)

            features = "".join(f"<li>{html.escape(str(item))}</li>" for item in app.get("features", [])[:6])
            release = "".join(f"<li>{html.escape(str(item))}</li>" for item in app.get("release_notes", [])[:4])
            permissions = html.escape(", ".join(app.get("permissions", [])) or "No special permissions declared")
            homepage = app.get("homepage", "")
            details_html = f"""
            <p>{html.escape(app.get('description') or app.get('summary') or 'No description available.')}</p>
            <p><b>License:</b> {html.escape(app.get('license') or 'Unspecified')}<br>
            <b>Permissions:</b> {permissions}<br>
            <b>Source:</b> {html.escape(app.get('source_name', app.get('source_id', 'Source')))}</p>
            """
            if homepage:
                details_html += f'<p><a href="{html.escape(homepage)}">{html.escape(homepage)}</a></p>'
            if features:
                details_html += f"<p><b>Highlights</b></p><ul>{features}</ul>"
            if release:
                details_html += f"<p><b>Release Notes</b></p><ul>{release}</ul>"
            self.detail_desc.setHtml(details_html)
            self.update_preview(app)
            self.update_actions()

        def resolve_asset(self, app: dict) -> Path | None:
            values = []
            if app.get("hero_image"):
                values.append(app["hero_image"])
            values.extend(app.get("screenshots", []))
            asset_base = Path(app.get("asset_base", ""))
            for value in values:
                raw = Path(str(value))
                candidates = []
                if raw.is_absolute():
                    candidates.append(raw)
                if asset_base:
                    candidates.append(asset_base / raw)
                    candidates.append(asset_base / raw.name)
                    if len(raw.parts) > 1:
                        candidates.append(asset_base.parent.parent / raw)
                for candidate in candidates:
                    if candidate.exists() and candidate.is_file():
                        return candidate
            return None

        def update_preview(self, app: dict) -> None:
            asset = self.resolve_asset(app)
            if asset:
                pixmap = QtGui.QPixmap(str(asset))
                if not pixmap.isNull():
                    self.preview.setPixmap(pixmap.scaled(self.preview.size(), QtCore.Qt.KeepAspectRatioByExpanding, QtCore.Qt.SmoothTransformation))
                    self.preview.setText("")
                    return
            self.preview.setPixmap(QtGui.QPixmap())
            self.preview.setText(app.get("name", "Foundry"))

        def update_actions(self) -> None:
            app = self.selected_app or {}
            has_app = bool(app.get("id")) and not app.get("error")
            self.install_btn.setEnabled(has_app)
            self.launch_btn.setEnabled(has_app and bool(app.get("installed")))
            self.remove_btn.setEnabled(has_app and bool(app.get("installed")))
            scopes = app.get("install_scopes", ["user"])
            for index in range(self.scope_combo.count()):
                value = self.scope_combo.itemData(index)
                self.scope_combo.model().item(index).setEnabled(value in scopes)
            if "user" in scopes:
                self.scope_combo.setCurrentIndex(self.scope_combo.findData("user"))
            elif scopes:
                found = self.scope_combo.findData(scopes[0])
                if found >= 0:
                    self.scope_combo.setCurrentIndex(found)

        def set_busy(self, busy: bool, message: str = "") -> None:
            if busy:
                self.progress.setRange(0, 0)
                if message:
                    self.set_status(message)
            else:
                self.progress.setRange(0, 100)
                self.progress.setValue(0)
            for widget in (self.install_btn, self.launch_btn, self.remove_btn, self.upgrade_btn, self.add_source_btn, self.remove_source_btn, self.refresh_source_btn):
                widget.setEnabled(not busy)

        def set_status(self, message: str, error: bool = False) -> None:
            self.status.setText(message)
            self.status.setStyleSheet("color: #f08f79;" if error else "color: #aec0ba;")

        def append_log(self, lines) -> None:
            if isinstance(lines, str):
                lines = [lines]
            for line in lines or []:
                text = str(line).strip()
                if text:
                    self.log.append(text)

        def start_job(self, request: dict, message: str, on_success=None, timeout: int = 240) -> None:
            backend = self.current_backend()
            if backend is None:
                self.set_status("No backend selected", error=True)
                return
            self.log.clear()
            self.set_busy(True, message)
            self.active_job = BackendJob(backend, request, timeout=timeout, parent=self)

            def finished(payload: dict) -> None:
                self.set_busy(False)
                self.update_actions()
                self.progress.setValue(int(payload.get("progress", 100 if payload.get("ok") else 0)))
                self.append_log(payload.get("log", []))
                if payload.get("ok"):
                    self.set_status(str(payload.get("message", "Done")))
                    if callable(on_success):
                        on_success(payload)
                else:
                    self.set_status(str(payload.get("error") or payload.get("message") or "Operation failed"), error=True)
                self.active_job = None

            self.active_job.finished_payload.connect(finished)
            self.active_job.start()

        def install_selected(self) -> None:
            if not self.selected_app:
                return
            scope = str(self.scope_combo.currentData() or "user")
            self.start_job(
                {
                    "action": "install",
                    "app_id": self.selected_app.get("id", ""),
                    "source_id": self.selected_app.get("source_id", self.selected_source_id()),
                    "scope": scope,
                },
                f"Installing {self.selected_app.get('name', 'app')}...",
                on_success=lambda _payload: self.load_apps(),
            )

        def remove_selected(self) -> None:
            if not self.selected_app:
                return
            scope = str(self.scope_combo.currentData() or "user")
            self.start_job(
                {"action": "remove", "app_id": self.selected_app.get("id", ""), "scope": scope},
                f"Removing {self.selected_app.get('name', 'app')}...",
                on_success=lambda _payload: self.load_apps(),
            )

        def launch_selected(self) -> None:
            if not self.selected_app:
                return
            self.start_job(
                {
                    "action": "launch",
                    "app_id": self.selected_app.get("id", ""),
                    "source_id": self.selected_app.get("source_id", self.selected_source_id()),
                },
                f"Launching {self.selected_app.get('name', 'app')}...",
            )

        def upgrade_apps(self) -> None:
            scope = str(self.scope_combo.currentData() or "user")
            self.start_job(
                {"action": "upgrade", "source_id": self.selected_source_id(), "scope": scope},
                "Checking installed apps...",
                on_success=lambda _payload: self.load_apps(),
            )

        def refresh_source(self) -> None:
            self.start_job(
                {"action": "refresh-source", "source_id": self.selected_source_id()},
                "Refreshing source...",
                on_success=lambda _payload: self.reload_everything(),
            )

        def add_source(self) -> None:
            url, ok = QtWidgets.QInputDialog.getText(self, "Add Source", "Signed repository URL")
            if not ok or not url.strip():
                return
            name, ok = QtWidgets.QInputDialog.getText(self, "Add Source", "Display name")
            if not ok:
                return
            self.start_job(
                {"action": "add-source", "url": url.strip(), "name": name.strip() or url.strip()},
                "Adding signed source...",
                on_success=lambda _payload: self.reload_everything(),
            )

        def remove_source(self) -> None:
            source_id = self.selected_source_id()
            if source_id in ("all", DEFAULT_BACKEND):
                self.set_status("Select a removable source first.", error=True)
                return
            confirm = QtWidgets.QMessageBox.question(self, "Remove Source", f"Remove source {source_id}?")
            if confirm != QtWidgets.QMessageBox.Yes:
                return
            self.start_job(
                {"action": "remove-source", "source_id": source_id},
                "Removing source...",
                on_success=lambda _payload: self.reload_everything(),
            )


def run_gui() -> int:
    if QT_IMPORT_ERROR is not None:
        print(f"{APP_NAME} requires python3-pyside2.qtwidgets: {QT_IMPORT_ERROR}", file=sys.stderr)
        return 1
    app = QtWidgets.QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    QtGui.QIcon.setThemeName("CRIXA-Depth")
    if not QtGui.QIcon.hasThemeIcon("system-software-install"):
        QtGui.QIcon.setThemeName("hicolor")
    window = StoreWindow()
    window.show()
    return int(app.exec_())


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="CRIXA Foundry software center")
    parser.add_argument("--self-test", action="store_true", help="validate store runtime without opening the UI")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.self_test:
        return self_test()
    return run_gui()


if __name__ == "__main__":
    raise SystemExit(main())
