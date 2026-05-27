#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

try:
    from PySide2 import QtCore, QtGui, QtWidgets

    QT_IMPORT_ERROR: Exception | None = None
except Exception as exc:  # pragma: no cover - depends on host packages
    class _MissingQtWidgets:
        QMainWindow = object

    class _MissingQtCore:
        class QProcess:
            class ExitStatus:
                pass

    QtCore = _MissingQtCore()  # type: ignore[assignment]
    QtGui = object()  # type: ignore[assignment]
    QtWidgets = _MissingQtWidgets()  # type: ignore[assignment]
    QT_IMPORT_ERROR = exc


APP_NAME = "Transit"
STATE_DIR = Path(os.environ.get("XDG_STATE_HOME", str(Path.home() / ".local" / "state"))) / "crixa-updater"
STAGED_PLAN = STATE_DIR / "staged-plan.json"


def first_existing(paths: list[Path]) -> Path:
    for path in paths:
        if path.exists():
            return path
    return paths[0]


RELEASECTL = first_existing([Path("/usr/local/bin/crixa-releasectl"), Path(__file__).resolve().with_name("crixa-releasectl.py")])
CRIXAPKG = first_existing([Path("/usr/local/bin/crixapkg"), Path(__file__).resolve().with_name("crixapkg.py")])
HELPER = first_existing([Path("/usr/lib/crixa-updater/crixa-updater-helper.py"), Path(__file__).resolve().with_name("crixa-updater-helper.py")])


def command_for(path: Path) -> list[str]:
    if path.suffix == ".py" and not os.access(path, os.X_OK):
        return [sys.executable, str(path)]
    if path.suffix == ".sh" and not os.access(path, os.X_OK):
        return ["bash", str(path)]
    return [str(path)]


def release_cmd() -> list[str]:
    return command_for(RELEASECTL)


def pkg_cmd() -> list[str]:
    return command_for(CRIXAPKG)


def helper_cmd() -> list[str]:
    return command_for(HELPER)


def run_cmd(args: list[str], timeout: int = 45) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, capture_output=True, text=True, check=False, timeout=timeout)


def run_json(args: list[str], timeout: int = 45) -> dict:
    result = run_cmd(args, timeout=timeout)
    if result.returncode != 0:
        raise RuntimeError((result.stderr or result.stdout).strip() or f"command failed: {' '.join(args)}")
    try:
        return json.loads(result.stdout or "{}")
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"invalid JSON from {' '.join(args)}") from exc


def run_json_status(args: list[str], timeout: int = 45) -> dict:
    result = run_cmd(args, timeout=timeout)
    try:
        payload = json.loads(result.stdout or "{}")
    except json.JSONDecodeError as exc:
        raise RuntimeError((result.stderr or result.stdout).strip() or f"invalid JSON from {' '.join(args)}") from exc
    if result.returncode != 0 and not payload:
        raise RuntimeError((result.stderr or result.stdout).strip() or f"command failed: {' '.join(args)}")
    return payload


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


def pending_package_updates(installed: list[dict], available: list[dict]) -> list[dict]:
    avail_map = {str(item.get("id", "")): item for item in available if isinstance(item, dict)}
    pending: list[dict] = []
    for app in installed:
        if not isinstance(app, dict):
            continue
        app_id = str(app.get("id", ""))
        installed_ver = str(app.get("version", "0"))
        repo_item = avail_map.get(app_id)
        if not repo_item:
            continue
        repo_ver = str(repo_item.get("version", "0"))
        if version_key(repo_ver) > version_key(installed_ver):
            pending.append(
                {
                    "id": app_id,
                    "name": str(app.get("name") or repo_item.get("name") or app_id),
                    "installed": installed_ver,
                    "available": repo_ver,
                    "scope": str(app.get("scope", "user")),
                }
            )
    return pending


def load_json_file(path: Path, default: dict) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return dict(default)


def save_json_file(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def collect_plan() -> dict:
    errors: list[str] = []
    try:
        repo_verify = run_json_status(pkg_cmd() + ["verify", "--json"])
        if not repo_verify.get("ok", False):
            errors.append(f"Package repo: {repo_verify.get('message') or repo_verify.get('error') or 'signature verification failed'}")
    except Exception as exc:
        repo_verify = {"ok": False, "message": str(exc)}
        errors.append(f"Package repo: {exc}")

    try:
        installed = run_json(pkg_cmd() + ["installed", "--json"]).get("apps", [])
    except Exception as exc:
        installed = []
        errors.append(f"Installed apps: {exc}")

    try:
        list_payload = run_json_status(pkg_cmd() + ["list", "--json"])
        if not list_payload.get("ok", True):
            errors.append(f"Available apps: {list_payload.get('error') or 'package list unavailable'}")
        available = list_payload.get("packages", [])
    except Exception as exc:
        available = []
        errors.append(f"Available apps: {exc}")

    try:
        release_plan = run_json_status(release_cmd() + ["plan", "--json"])
        if not release_plan.get("ok", False):
            errors.append(f"System rollout: {release_plan.get('error') or 'rollout plan unavailable'}")
    except Exception as exc:
        release_plan = {"ok": False, "error": str(exc), "plan": {"actionable": False, "reason": str(exc)}}
        errors.append(f"System rollout: {exc}")

    try:
        history = run_json(pkg_cmd() + ["history", "--json"]).get("snapshots", [])
    except Exception as exc:
        history = []
        errors.append(f"Snapshots: {exc}")

    pending = pending_package_updates(
        [row for row in installed if isinstance(row, dict)],
        [row for row in available if isinstance(row, dict)],
    )
    return {
        "ok": not errors,
        "errors": errors,
        "repo": repo_verify,
        "installed": installed,
        "available": available,
        "package_updates": pending,
        "release": release_plan,
        "snapshots": [row for row in history if isinstance(row, dict)],
    }


def stylesheet() -> str:
    return """
    QWidget {
      background: #101721;
      color: #edf2f7;
      font-family: "Inter", "DejaVu Sans", sans-serif;
      font-size: 10.5pt;
    }
    QLabel#Title { font-size: 24px; font-weight: 700; color: #ffffff; }
    QLabel#Subtitle { color: #9fb1c6; }
    QLabel#Card {
      background: #172230;
      border: 1px solid #27364a;
      border-radius: 8px;
      padding: 12px;
      font-weight: 600;
    }
    QFrame#Panel {
      background: #141f2c;
      border: 1px solid #263549;
      border-radius: 8px;
    }
    QTabWidget::pane { border: 1px solid #263549; border-radius: 8px; top: -1px; }
    QTabBar::tab {
      background: #172230;
      border: 1px solid #263549;
      border-bottom: 0;
      padding: 9px 14px;
      margin-right: 4px;
      border-top-left-radius: 7px;
      border-top-right-radius: 7px;
    }
    QTabBar::tab:selected { background: #223247; color: white; }
    QTableWidget, QTextEdit {
      background: #0c131d;
      border: 1px solid #263549;
      border-radius: 8px;
      gridline-color: #263549;
      selection-background-color: #2f7dd1;
    }
    QHeaderView::section {
      background: #192536;
      color: #dbe7f5;
      border: 0;
      padding: 7px;
      font-weight: 600;
    }
    QPushButton {
      background: #223247;
      border: 1px solid #344860;
      border-radius: 7px;
      padding: 8px 12px;
      font-weight: 600;
    }
    QPushButton:hover { background: #2b405b; }
    QPushButton#Primary { background: #2f7dd1; border-color: #4e9beb; color: white; }
    QPushButton#Danger { background: #8f3434; border-color: #ba4f4f; color: white; }
    QPushButton:disabled { color: #6f7f91; background: #17202b; border-color: #253244; }
    QProgressBar {
      background: #0c131d;
      border: 1px solid #304158;
      border-radius: 6px;
      text-align: center;
      height: 20px;
    }
    QProgressBar::chunk { background: #5db7a7; border-radius: 5px; }
    """


class TransitWindow(QtWidgets.QMainWindow):  # type: ignore[misc]
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.resize(1140, 760)
        self.setMinimumSize(980, 680)
        self.current_plan: dict = {}
        self.snapshots: list[dict] = []
        self.proc: QtCore.QProcess | None = None
        self.process_output = ""

        self._build_ui()
        self.refresh_plan()

    def _build_ui(self) -> None:
        root = QtWidgets.QWidget()
        self.setCentralWidget(root)
        layout = QtWidgets.QVBoxLayout(root)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(14)

        header = QtWidgets.QHBoxLayout()
        title_col = QtWidgets.QVBoxLayout()
        title = QtWidgets.QLabel("Transit")
        title.setObjectName("Title")
        subtitle = QtWidgets.QLabel("Signed update planning, staged package transactions, and visible rollback snapshots.")
        subtitle.setObjectName("Subtitle")
        title_col.addWidget(title)
        title_col.addWidget(subtitle)
        header.addLayout(title_col, 1)
        self.refresh_btn = QtWidgets.QPushButton(QtGui.QIcon.fromTheme("view-refresh"), "Refresh")
        self.refresh_btn.clicked.connect(self.refresh_plan)
        header.addWidget(self.refresh_btn)
        layout.addLayout(header)

        cards = QtWidgets.QHBoxLayout()
        self.repo_card = QtWidgets.QLabel("Repository\nUnknown")
        self.repo_card.setObjectName("Card")
        self.pkg_card = QtWidgets.QLabel("Package updates\n0 pending")
        self.pkg_card.setObjectName("Card")
        self.track_card = QtWidgets.QLabel("Track\nUnknown")
        self.track_card.setObjectName("Card")
        self.snapshot_card = QtWidgets.QLabel("Rollback\n0 snapshots")
        self.snapshot_card.setObjectName("Card")
        for card in (self.repo_card, self.pkg_card, self.track_card, self.snapshot_card):
            cards.addWidget(card)
        layout.addLayout(cards)

        self.tabs = QtWidgets.QTabWidget()
        layout.addWidget(self.tabs, 1)
        self._build_plan_tab()
        self._build_apply_tab()
        self._build_history_tab()
        self._build_channels_tab()

        self.status = QtWidgets.QLabel("Ready")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)

    def _panel(self) -> tuple[QtWidgets.QFrame, QtWidgets.QVBoxLayout]:
        frame = QtWidgets.QFrame()
        frame.setObjectName("Panel")
        box = QtWidgets.QVBoxLayout(frame)
        box.setContentsMargins(12, 12, 12, 12)
        box.setSpacing(10)
        return frame, box

    def _build_plan_tab(self) -> None:
        tab = QtWidgets.QWidget()
        layout = QtWidgets.QHBoxLayout(tab)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(12)

        pkg_panel, pkg_layout = self._panel()
        pkg_layout.addWidget(QtWidgets.QLabel("Pending Package Updates"))
        self.pkg_table = QtWidgets.QTableWidget(0, 5)
        self.pkg_table.setHorizontalHeaderLabels(["App", "Name", "Installed", "Available", "Scope"])
        self.pkg_table.horizontalHeader().setStretchLastSection(True)
        self.pkg_table.horizontalHeader().setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeToContents)
        self.pkg_table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.pkg_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        pkg_layout.addWidget(self.pkg_table, 1)
        layout.addWidget(pkg_panel, 3)

        release_panel, release_layout = self._panel()
        release_layout.addWidget(QtWidgets.QLabel("System Rollout Plan"))
        self.release_summary = QtWidgets.QTextEdit()
        self.release_summary.setReadOnly(True)
        release_layout.addWidget(self.release_summary, 1)
        btn_row = QtWidgets.QHBoxLayout()
        self.stage_btn = QtWidgets.QPushButton(QtGui.QIcon.fromTheme("document-save"), "Stage Plan")
        self.stage_btn.setObjectName("Primary")
        self.stage_btn.clicked.connect(self.stage_plan)
        self.verify_btn = QtWidgets.QPushButton(QtGui.QIcon.fromTheme("security-high"), "Verify Signatures")
        self.verify_btn.clicked.connect(self.verify_signatures)
        btn_row.addWidget(self.stage_btn)
        btn_row.addWidget(self.verify_btn)
        release_layout.addLayout(btn_row)
        layout.addWidget(release_panel, 2)
        self.tabs.addTab(tab, QtGui.QIcon.fromTheme("view-list-details"), "Plan")

    def _build_apply_tab(self) -> None:
        tab = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(tab)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(12)
        staged_panel, staged_layout = self._panel()
        staged_layout.addWidget(QtWidgets.QLabel("Staged Update"))
        self.staged_summary = QtWidgets.QTextEdit()
        self.staged_summary.setReadOnly(True)
        staged_layout.addWidget(self.staged_summary)
        action_row = QtWidgets.QHBoxLayout()
        self.apply_btn = QtWidgets.QPushButton(QtGui.QIcon.fromTheme("system-software-update"), "Apply Staged Updates")
        self.apply_btn.setObjectName("Primary")
        self.apply_btn.clicked.connect(self.apply_staged)
        self.clear_stage_btn = QtWidgets.QPushButton(QtGui.QIcon.fromTheme("edit-clear"), "Clear Stage")
        self.clear_stage_btn.clicked.connect(self.clear_stage)
        action_row.addWidget(self.apply_btn)
        action_row.addWidget(self.clear_stage_btn)
        action_row.addStretch(1)
        staged_layout.addLayout(action_row)
        layout.addWidget(staged_panel, 1)

        log_panel, log_layout = self._panel()
        log_layout.addWidget(QtWidgets.QLabel("Operation Log"))
        self.progress = QtWidgets.QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        log_layout.addWidget(self.progress)
        self.log = QtWidgets.QTextEdit()
        self.log.setReadOnly(True)
        log_layout.addWidget(self.log, 1)
        layout.addWidget(log_panel, 2)
        self.tabs.addTab(tab, QtGui.QIcon.fromTheme("system-run"), "Apply")

    def _build_history_tab(self) -> None:
        tab = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(tab)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(12)
        panel, panel_layout = self._panel()
        panel_layout.addWidget(QtWidgets.QLabel("Rollback Snapshots"))
        self.snapshot_table = QtWidgets.QTableWidget(0, 5)
        self.snapshot_table.setHorizontalHeaderLabels(["Snapshot", "Created", "Reason", "Tracked", "Copied"])
        self.snapshot_table.horizontalHeader().setStretchLastSection(True)
        self.snapshot_table.horizontalHeader().setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeToContents)
        self.snapshot_table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.snapshot_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        panel_layout.addWidget(self.snapshot_table, 1)
        row = QtWidgets.QHBoxLayout()
        self.rollback_selected_btn = QtWidgets.QPushButton(QtGui.QIcon.fromTheme("edit-undo"), "Rollback Selected")
        self.rollback_selected_btn.clicked.connect(self.rollback_selected)
        self.rollback_latest_btn = QtWidgets.QPushButton(QtGui.QIcon.fromTheme("media-seek-backward"), "Rollback Latest")
        self.rollback_latest_btn.clicked.connect(lambda: self.rollback_to("latest"))
        row.addWidget(self.rollback_selected_btn)
        row.addWidget(self.rollback_latest_btn)
        row.addStretch(1)
        panel_layout.addLayout(row)
        layout.addWidget(panel)
        self.tabs.addTab(tab, QtGui.QIcon.fromTheme("document-revert"), "History")

    def _build_channels_tab(self) -> None:
        tab = QtWidgets.QWidget()
        layout = QtWidgets.QHBoxLayout(tab)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(12)
        panel, panel_layout = self._panel()
        panel_layout.addWidget(QtWidgets.QLabel("Release Track"))
        self.channel_summary = QtWidgets.QTextEdit()
        self.channel_summary.setReadOnly(True)
        panel_layout.addWidget(self.channel_summary, 1)
        btns = QtWidgets.QHBoxLayout()
        for track in ("stable", "beta", "canary"):
            btn = QtWidgets.QPushButton(track.title())
            btn.clicked.connect(lambda _checked=False, value=track: self.switch_track(value))
            btns.addWidget(btn)
        btns.addStretch(1)
        panel_layout.addLayout(btns)
        layout.addWidget(panel)
        self.tabs.addTab(tab, QtGui.QIcon.fromTheme("network-server"), "Channels")

    def append_log(self, text: str) -> None:
        if not text:
            return
        self.log.append(text.rstrip())
        self.log.moveCursor(QtGui.QTextCursor.End)

    def set_busy(self, busy: bool, message: str | None = None) -> None:
        for widget in (
            self.refresh_btn,
            self.stage_btn,
            self.verify_btn,
            self.apply_btn,
            self.clear_stage_btn,
            self.rollback_selected_btn,
            self.rollback_latest_btn,
        ):
            widget.setEnabled(not busy)
        self.progress.setRange(0, 0 if busy else 100)
        if not busy:
            self.progress.setValue(0)
        if message:
            self.status.setText(message)

    def refresh_plan(self) -> None:
        self.set_busy(True, "Refreshing update plan...")
        try:
            self.current_plan = collect_plan()
            self.snapshots = [row for row in self.current_plan.get("snapshots", []) if isinstance(row, dict)]
            self.render_plan()
            self.status.setText("Update state refreshed." if self.current_plan.get("ok") else "Refresh completed with warnings.")
        except Exception as exc:
            self.status.setText(f"Refresh failed: {exc}")
            self.append_log(f"Refresh failed: {exc}")
        finally:
            self.set_busy(False)

    def render_plan(self) -> None:
        repo = self.current_plan.get("repo", {})
        repo_ok = bool(repo.get("ok", False))
        package_updates = [row for row in self.current_plan.get("package_updates", []) if isinstance(row, dict)]
        release = self.current_plan.get("release", {})
        release_plan = release.get("plan", {}) if isinstance(release, dict) else {}
        current = release.get("current", {}) if isinstance(release, dict) else {}
        track = str(release_plan.get("track") or current.get("track") or "unknown")

        self.repo_card.setText(f"Repository\n{'Signed' if repo_ok else 'Needs attention'}")
        self.pkg_card.setText(f"Package updates\n{len(package_updates)} pending")
        self.track_card.setText(f"Track\n{track}")
        self.snapshot_card.setText(f"Rollback\n{len(self.snapshots)} snapshots")

        self.pkg_table.setRowCount(len(package_updates))
        for row, item in enumerate(package_updates):
            values = [
                str(item.get("id", "")),
                str(item.get("name", "")),
                str(item.get("installed", "")),
                str(item.get("available", "")),
                str(item.get("scope", "user")),
            ]
            for col, value in enumerate(values):
                self.pkg_table.setItem(row, col, QtWidgets.QTableWidgetItem(value))

        errors = self.current_plan.get("errors", [])
        lines = [
            f"Current: {release_plan.get('current_version', current.get('version', 'unknown'))}",
            f"Target: {release_plan.get('target_version', 'unknown')}",
            f"Eligible: {'yes' if release_plan.get('eligible') else 'no'}",
            f"Actionable system payload: {'yes' if release_plan.get('actionable') else 'no'}",
            f"Reason: {release_plan.get('reason', release.get('error', 'unknown'))}",
        ]
        if errors:
            lines.append("")
            lines.append("Warnings:")
            lines.extend(f"- {err}" for err in errors)
        self.release_summary.setPlainText("\n".join(lines))
        self.channel_summary.setPlainText("\n".join(lines))

        self.snapshot_table.setRowCount(len(self.snapshots))
        for row, snap in enumerate(self.snapshots):
            values = [
                str(snap.get("id", "")),
                str(snap.get("created_at", "")),
                str(snap.get("reason", "")),
                str(snap.get("tracked_files", "")),
                str(snap.get("copied_files", "")),
            ]
            for col, value in enumerate(values):
                self.snapshot_table.setItem(row, col, QtWidgets.QTableWidgetItem(value))
        self.render_staged()

    def render_staged(self) -> None:
        staged = load_json_file(STAGED_PLAN, {})
        if not staged:
            self.staged_summary.setPlainText("No staged update plan.")
            return
        packages = staged.get("package_updates", [])
        release = staged.get("release", {}).get("plan", {}) if isinstance(staged.get("release"), dict) else {}
        lines = [
            f"Packages staged: {len(packages) if isinstance(packages, list) else 0}",
            f"System target: {release.get('target_version', 'none')}",
            f"System actionable: {'yes' if release.get('actionable') else 'no'}",
        ]
        if isinstance(packages, list) and packages:
            lines.append("")
            lines.extend(f"- {pkg.get('id', '')}: {pkg.get('installed', '')} -> {pkg.get('available', '')}" for pkg in packages)
        self.staged_summary.setPlainText("\n".join(lines))

    def stage_plan(self) -> None:
        if not self.current_plan:
            self.refresh_plan()
        payload = {
            "package_updates": self.current_plan.get("package_updates", []),
            "release": self.current_plan.get("release", {}),
            "repo": self.current_plan.get("repo", {}),
        }
        save_json_file(STAGED_PLAN, payload)
        self.render_staged()
        self.status.setText(f"Plan staged at {STAGED_PLAN}.")
        self.append_log(f"Staged plan: {STAGED_PLAN}")

    def clear_stage(self) -> None:
        try:
            STAGED_PLAN.unlink()
        except FileNotFoundError:
            pass
        self.render_staged()
        self.status.setText("Staged plan cleared.")

    def verify_signatures(self) -> None:
        self.start_operation(pkg_cmd() + ["verify", "--json"], "Verifying package repository signature...", refresh_after=False)

    def apply_staged(self) -> None:
        staged = load_json_file(STAGED_PLAN, {})
        packages = staged.get("package_updates", [])
        if not packages:
            QtWidgets.QMessageBox.information(self, APP_NAME, "There are no staged package updates to apply.")
            return
        answer = QtWidgets.QMessageBox.question(
            self,
            "Apply Updates",
            f"Apply {len(packages)} package update(s)? Transit will create a crixapkg snapshot before changes.",
        )
        if answer != QtWidgets.QMessageBox.Yes:
            return
        self.start_operation(pkg_cmd() + ["upgrade", "--json"], "Applying staged package updates...", refresh_after=True)

    def selected_snapshot(self) -> str:
        rows = self.snapshot_table.selectionModel().selectedRows()
        if not rows:
            return ""
        idx = rows[0].row()
        if idx < 0 or idx >= len(self.snapshots):
            return ""
        return str(self.snapshots[idx].get("id", ""))

    def rollback_selected(self) -> None:
        snap_id = self.selected_snapshot()
        if not snap_id:
            QtWidgets.QMessageBox.information(self, APP_NAME, "Select a snapshot first.")
            return
        self.rollback_to(snap_id)

    def rollback_to(self, snap_id: str) -> None:
        answer = QtWidgets.QMessageBox.question(self, "Confirm Rollback", f"Rollback using snapshot {snap_id}?")
        if answer != QtWidgets.QMessageBox.Yes:
            return
        self.start_operation(pkg_cmd() + ["rollback", snap_id, "--json"], f"Rolling back {snap_id}...", refresh_after=True)

    def switch_track(self, track: str) -> None:
        answer = QtWidgets.QMessageBox.question(self, "Switch Track", f"Switch release track to {track}?")
        if answer != QtWidgets.QMessageBox.Yes:
            return
        if os.geteuid() == 0:
            cmd = release_cmd() + ["switch-track", track, "--json"]
        elif HELPER.exists() and shutil.which("pkexec"):
            cmd = ["pkexec"] + helper_cmd() + ["switch-track", track, "--json"]
        else:
            QtWidgets.QMessageBox.critical(self, APP_NAME, "Transit needs pkexec and the release-track helper to switch tracks.")
            return
        self.start_operation(cmd, f"Switching track to {track}...", refresh_after=True)

    def start_operation(self, cmd: list[str], message: str, refresh_after: bool) -> None:
        if self.proc is not None:
            return
        self.tabs.setCurrentIndex(1)
        self.append_log("\n$ " + " ".join(cmd))
        self.process_output = ""
        self.set_busy(True, message)
        self.proc = QtCore.QProcess(self)
        self.proc.setProgram(cmd[0])
        self.proc.setArguments(cmd[1:])
        self.proc.setProperty("refresh_after", refresh_after)
        self.proc.readyReadStandardOutput.connect(self.read_stdout)
        self.proc.readyReadStandardError.connect(self.read_stderr)
        self.proc.finished.connect(self.process_finished)
        self.proc.start()
        if not self.proc.waitForStarted(1500):
            self.append_log(f"Failed to start: {cmd[0]}")
            self.proc = None
            self.set_busy(False, "Failed to start operation.")

    def read_stdout(self) -> None:
        if self.proc is None:
            return
        text = bytes(self.proc.readAllStandardOutput()).decode(errors="replace")
        self.process_output += text
        if text.strip():
            self.append_log(text)

    def read_stderr(self) -> None:
        if self.proc is None:
            return
        text = bytes(self.proc.readAllStandardError()).decode(errors="replace")
        if text.strip():
            self.append_log(text)

    def process_finished(self, code: int, _status: QtCore.QProcess.ExitStatus) -> None:
        refresh_after = bool(self.proc.property("refresh_after")) if self.proc is not None else False
        self.proc = None
        self.set_busy(False)
        if code == 0:
            self.status.setText("Operation completed.")
            self.progress.setValue(100)
            if refresh_after:
                self.refresh_plan()
        else:
            self.status.setText(f"Operation failed with exit code {code}.")


def run_self_test() -> int:
    checks: list[tuple[str, bool, str]] = [
        ("PySide2", QT_IMPORT_ERROR is None, str(QT_IMPORT_ERROR or "available")),
        ("crixapkg", CRIXAPKG.exists() or shutil.which("crixapkg") is not None, str(CRIXAPKG)),
        ("crixa-releasectl", RELEASECTL.exists() or shutil.which("crixa-releasectl") is not None, str(RELEASECTL)),
        ("release helper", HELPER.exists(), str(HELPER)),
        ("pkexec", shutil.which("pkexec") is not None or os.geteuid() == 0, "pkexec available or already root"),
    ]
    ok = True
    for name, passed, detail in checks:
        required = name != "pkexec"
        ok = ok and (passed or not required)
        state = "ok" if passed else ("warn" if not required else "fail")
        print(f"{state}: {name} - {detail}")
    try:
        plan = collect_plan()
        print(f"ok: update plan - {len(plan.get('package_updates', []))} package update(s)")
        if plan.get("errors"):
            print("warn: update plan warnings - " + "; ".join(str(err) for err in plan.get("errors", [])))
    except Exception as exc:
        ok = False
        print(f"fail: update plan - {exc}")
    try:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        probe = STATE_DIR / ".self-test"
        probe.write_text("ok\n", encoding="utf-8")
        probe.unlink()
        print(f"ok: state directory - {STATE_DIR}")
    except Exception as exc:
        ok = False
        print(f"fail: state directory - {exc}")
    return 0 if ok else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="CRIXA Transit updater")
    parser.add_argument("--self-test", action="store_true", help="validate Transit dependencies and backend access")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    if args.self_test:
        return run_self_test()
    if QT_IMPORT_ERROR is not None:
        print(f"{APP_NAME} requires python3-pyside2.qtwidgets: {QT_IMPORT_ERROR}", file=sys.stderr)
        return 1
    app = QtWidgets.QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setWindowIcon(QtGui.QIcon.fromTheme("crixa-updater"))
    app.setStyleSheet(stylesheet())
    window = TransitWindow()
    window.show()
    return int(app.exec_())


if __name__ == "__main__":
    raise SystemExit(main())
