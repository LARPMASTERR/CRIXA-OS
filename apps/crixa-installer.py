#!/usr/bin/env python3
from __future__ import annotations

import argparse
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


APP_NAME = "Dockyard"
DEFAULT_LOG = "/var/log/crixa-installer.log"


def first_existing(paths: list[Path]) -> Path:
    for path in paths:
        if path.exists():
            return path
    return paths[0]


INSTALLER_BIN = first_existing([Path("/usr/local/sbin/crixa-install"), Path(__file__).resolve().with_name("crixa-install.sh")])
HELPER_BIN = first_existing(
    [Path("/usr/lib/crixa-installer/crixa-installer-helper.py"), Path(__file__).resolve().with_name("crixa-installer-helper.py")]
)


@dataclass
class DiskInfo:
    path: str
    size: str
    model: str
    transport: str
    removable: bool
    rotational: bool
    serial: str
    mounted_children: list[str]

    @property
    def kind(self) -> str:
        if self.removable:
            return "Removable"
        if self.rotational:
            return "Hard disk"
        return "Solid-state"

    @property
    def risk(self) -> str:
        mounted = ", ".join(self.mounted_children)
        if mounted:
            return f"Mounted partitions detected: {mounted}"
        return "Ready for guided full-disk install"


def command_for(path: Path) -> list[str]:
    if path.suffix == ".py" and not os.access(path, os.X_OK):
        return [sys.executable, str(path)]
    if path.suffix == ".sh" and not os.access(path, os.X_OK):
        return ["bash", str(path)]
    return [str(path)]


def installer_command() -> list[str]:
    return command_for(INSTALLER_BIN)


def helper_command() -> list[str]:
    return command_for(HELPER_BIN)


def run_cmd(args: list[str], timeout: int = 30) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, capture_output=True, text=True, check=False, timeout=timeout)


def run_json(args: list[str], timeout: int = 30) -> dict:
    result = run_cmd(args, timeout=timeout)
    if result.returncode != 0:
        raise RuntimeError((result.stderr or result.stdout).strip() or f"command failed: {' '.join(args)}")
    try:
        return json.loads(result.stdout or "{}")
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"invalid JSON from {' '.join(args)}") from exc


def probe_disks() -> list[DiskInfo]:
    payload = run_json(installer_command() + ["--probe", "--json"])
    rows: list[DiskInfo] = []
    for item in payload.get("disks", []):
        if not isinstance(item, dict):
            continue
        rows.append(
            DiskInfo(
                path=str(item.get("path", "")),
                size=str(item.get("size", "?")),
                model=str(item.get("model", "Unknown")),
                transport=str(item.get("transport", "")),
                removable=bool(item.get("removable", False)),
                rotational=bool(item.get("rotational", False)),
                serial=str(item.get("serial", "")),
                mounted_children=[str(mp) for mp in item.get("mounted_children", []) if mp],
            )
        )
    return [row for row in rows if row.path]


def base_install_args(target: str, hostname: str, user: str, timezone: str, password: str, label: str = "CRIXA_ROOT") -> list[str]:
    args = [
        "--target",
        target,
        "--hostname",
        hostname or "crixa-os",
        "--user",
        user or "crixa",
        "--label",
        label or "CRIXA_ROOT",
        "--timezone",
        timezone or "UTC",
    ]
    if password:
        args += ["--user-password", password]
    return args


def build_install_command(target: str, hostname: str, user: str, timezone: str, password: str) -> list[str]:
    args = base_install_args(target, hostname, user, timezone, password)
    if os.geteuid() == 0:
        return installer_command() + args + ["--yes", "--json", "--log", DEFAULT_LOG]
    if HELPER_BIN.exists() and shutil.which("pkexec"):
        return ["pkexec"] + helper_command() + ["install"] + args + ["--log", DEFAULT_LOG]
    raise RuntimeError("Dockyard needs pkexec and the installer helper for privileged installs")


def build_dry_run_command(target: str, hostname: str, user: str, timezone: str, password: str) -> list[str]:
    return installer_command() + base_install_args(target, hostname, user, timezone, password) + ["--dry-run", "--yes", "--json"]


def stylesheet() -> str:
    return """
    QWidget {
      background: #101721;
      color: #edf2f7;
      font-family: "Inter", "DejaVu Sans", sans-serif;
      font-size: 10.5pt;
    }
    QMainWindow, QDialog { background: #101721; }
    QLabel#Title { font-size: 24px; font-weight: 700; color: #ffffff; }
    QLabel#Subtitle { color: #9fb1c6; }
    QLabel#Metric {
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
    QLineEdit {
      background: #0c131d;
      border: 1px solid #304158;
      border-radius: 6px;
      padding: 8px;
      selection-background-color: #2f7dd1;
    }
    QPushButton {
      background: #223247;
      border: 1px solid #344860;
      border-radius: 7px;
      padding: 8px 12px;
      font-weight: 600;
    }
    QPushButton:hover { background: #2b405b; }
    QPushButton:pressed { background: #1c2a3c; }
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


class DockyardWindow(QtWidgets.QMainWindow):  # type: ignore[misc]
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.resize(1120, 760)
        self.setMinimumSize(980, 680)
        self.disks: list[DiskInfo] = []
        self.proc: QtCore.QProcess | None = None
        self.output_buffer = ""

        self._build_ui()
        self.refresh_disks()

    def _build_ui(self) -> None:
        root = QtWidgets.QWidget()
        self.setCentralWidget(root)
        layout = QtWidgets.QVBoxLayout(root)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(14)

        header = QtWidgets.QHBoxLayout()
        title_col = QtWidgets.QVBoxLayout()
        title = QtWidgets.QLabel("Dockyard")
        title.setObjectName("Title")
        subtitle = QtWidgets.QLabel("Guided full-disk installs with dry-run preview, visible stages, and logged recovery details.")
        subtitle.setObjectName("Subtitle")
        title_col.addWidget(title)
        title_col.addWidget(subtitle)
        header.addLayout(title_col, 1)
        self.refresh_btn = QtWidgets.QPushButton(QtGui.QIcon.fromTheme("view-refresh"), "Refresh")
        self.refresh_btn.clicked.connect(self.refresh_disks)
        header.addWidget(self.refresh_btn)
        self.terminal_btn = QtWidgets.QPushButton(QtGui.QIcon.fromTheme("utilities-terminal"), "Terminal Mode")
        self.terminal_btn.clicked.connect(self.open_terminal_mode)
        header.addWidget(self.terminal_btn)
        layout.addLayout(header)

        metrics = QtWidgets.QHBoxLayout()
        self.disk_count = QtWidgets.QLabel("Disks\n0 detected")
        self.disk_count.setObjectName("Metric")
        self.target_metric = QtWidgets.QLabel("Target\nNone selected")
        self.target_metric.setObjectName("Metric")
        self.mode_metric = QtWidgets.QLabel("Mode\nGuided full-disk")
        self.mode_metric.setObjectName("Metric")
        metrics.addWidget(self.disk_count)
        metrics.addWidget(self.target_metric)
        metrics.addWidget(self.mode_metric)
        layout.addLayout(metrics)

        body = QtWidgets.QHBoxLayout()
        layout.addLayout(body, 1)

        left = QtWidgets.QFrame()
        left.setObjectName("Panel")
        left_layout = QtWidgets.QVBoxLayout(left)
        left_layout.setContentsMargins(12, 12, 12, 12)
        left_layout.addWidget(QtWidgets.QLabel("Install Target"))
        self.disk_table = QtWidgets.QTableWidget(0, 5)
        self.disk_table.setHorizontalHeaderLabels(["Device", "Size", "Model", "Kind", "State"])
        self.disk_table.horizontalHeader().setStretchLastSection(True)
        self.disk_table.horizontalHeader().setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeToContents)
        self.disk_table.horizontalHeader().setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeToContents)
        self.disk_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.disk_table.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        self.disk_table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.disk_table.itemSelectionChanged.connect(self.update_target_summary)
        left_layout.addWidget(self.disk_table, 1)
        self.risk_label = QtWidgets.QLabel("Select a disk to see install risk.")
        self.risk_label.setWordWrap(True)
        left_layout.addWidget(self.risk_label)
        body.addWidget(left, 3)

        right = QtWidgets.QFrame()
        right.setObjectName("Panel")
        right_layout = QtWidgets.QVBoxLayout(right)
        right_layout.setContentsMargins(12, 12, 12, 12)
        right_layout.addWidget(QtWidgets.QLabel("System Setup"))
        form = QtWidgets.QFormLayout()
        self.hostname = QtWidgets.QLineEdit("crixa-os")
        self.username = QtWidgets.QLineEdit("crixa")
        self.timezone = QtWidgets.QLineEdit("UTC")
        self.password = QtWidgets.QLineEdit()
        self.password.setEchoMode(QtWidgets.QLineEdit.Password)
        form.addRow("Hostname", self.hostname)
        form.addRow("Primary user", self.username)
        form.addRow("Timezone", self.timezone)
        form.addRow("Password", self.password)
        right_layout.addLayout(form)

        self.progress = QtWidgets.QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        right_layout.addWidget(self.progress)
        self.status = QtWidgets.QLabel("Ready")
        self.status.setWordWrap(True)
        right_layout.addWidget(self.status)

        actions = QtWidgets.QGridLayout()
        self.dry_run_btn = QtWidgets.QPushButton(QtGui.QIcon.fromTheme("document-preview"), "Dry Run")
        self.dry_run_btn.clicked.connect(self.start_dry_run)
        self.install_btn = QtWidgets.QPushButton(QtGui.QIcon.fromTheme("drive-harddisk"), "Install CRIXA")
        self.install_btn.setObjectName("Danger")
        self.install_btn.clicked.connect(self.start_install)
        self.log_btn = QtWidgets.QPushButton(QtGui.QIcon.fromTheme("text-x-log"), "Open Log")
        self.log_btn.clicked.connect(self.open_log)
        self.close_btn = QtWidgets.QPushButton("Close")
        self.close_btn.clicked.connect(self.close)
        actions.addWidget(self.dry_run_btn, 0, 0)
        actions.addWidget(self.install_btn, 0, 1)
        actions.addWidget(self.log_btn, 1, 0)
        actions.addWidget(self.close_btn, 1, 1)
        right_layout.addLayout(actions)
        right_layout.addStretch(1)
        body.addWidget(right, 2)

        log_panel = QtWidgets.QFrame()
        log_panel.setObjectName("Panel")
        log_layout = QtWidgets.QVBoxLayout(log_panel)
        log_layout.setContentsMargins(12, 12, 12, 12)
        log_layout.addWidget(QtWidgets.QLabel("Install Log"))
        self.log = QtWidgets.QTextEdit()
        self.log.setReadOnly(True)
        self.log.setMinimumHeight(150)
        self.log.append("Dockyard ready.")
        log_layout.addWidget(self.log)
        layout.addWidget(log_panel)

    def selected_disk(self) -> DiskInfo | None:
        rows = self.disk_table.selectionModel().selectedRows()
        if not rows:
            return None
        idx = rows[0].row()
        if idx < 0 or idx >= len(self.disks):
            return None
        return self.disks[idx]

    def refresh_disks(self) -> None:
        self.set_busy(True, "Scanning disks...")
        try:
            self.disks = probe_disks()
            self.populate_disks()
            self.status.setText(f"Detected {len(self.disks)} installable disk(s).")
            self.progress.setValue(0)
        except Exception as exc:
            self.status.setText(f"Disk scan failed: {exc}")
            self.append_log(f"Disk scan failed: {exc}")
        finally:
            self.set_busy(False)

    def populate_disks(self) -> None:
        self.disk_table.setRowCount(len(self.disks))
        for row, disk in enumerate(self.disks):
            state = "Mounted" if disk.mounted_children else "Available"
            values = [disk.path, disk.size, disk.model, disk.kind, state]
            for col, value in enumerate(values):
                item = QtWidgets.QTableWidgetItem(value)
                if state == "Mounted":
                    item.setForeground(QtGui.QColor("#f2b84b"))
                self.disk_table.setItem(row, col, item)
        if self.disks:
            self.disk_table.selectRow(0)
        self.disk_count.setText(f"Disks\n{len(self.disks)} detected")
        self.update_target_summary()

    def update_target_summary(self) -> None:
        disk = self.selected_disk()
        if disk is None:
            self.target_metric.setText("Target\nNone selected")
            self.risk_label.setText("Select a disk to see install risk.")
            return
        self.target_metric.setText(f"Target\n{disk.path}  {disk.size}")
        self.risk_label.setText(
            f"{disk.path} will be erased and repartitioned as BIOS boot, EFI, and ext4 root. {disk.risk}"
        )

    def append_log(self, text: str) -> None:
        if not text:
            return
        self.log.append(text.rstrip())
        self.log.moveCursor(QtGui.QTextCursor.End)

    def set_busy(self, busy: bool, message: str | None = None) -> None:
        for widget in (self.refresh_btn, self.terminal_btn, self.dry_run_btn, self.install_btn, self.log_btn, self.close_btn):
            widget.setEnabled(not busy)
        if message:
            self.status.setText(message)

    def current_values(self) -> tuple[str, str, str, str, str]:
        disk = self.selected_disk()
        if disk is None:
            raise RuntimeError("Select a target disk first")
        return (
            disk.path,
            self.hostname.text().strip() or "crixa-os",
            self.username.text().strip() or "crixa",
            self.timezone.text().strip() or "UTC",
            self.password.text(),
        )

    def start_dry_run(self) -> None:
        try:
            cmd = build_dry_run_command(*self.current_values())
        except Exception as exc:
            QtWidgets.QMessageBox.warning(self, APP_NAME, str(exc))
            return
        self.append_log("\n$ " + " ".join(cmd))
        self.start_process(cmd, "Dry-run preview running...")

    def start_install(self) -> None:
        try:
            target, hostname, user, timezone, password = self.current_values()
        except Exception as exc:
            QtWidgets.QMessageBox.warning(self, APP_NAME, str(exc))
            return
        first = QtWidgets.QMessageBox.question(
            self,
            "Confirm Install",
            f"Dockyard will erase all data on {target} and install CRIXA OS.\n\nContinue?",
        )
        if first != QtWidgets.QMessageBox.Yes:
            return
        typed, ok = QtWidgets.QInputDialog.getText(self, "Type ERASE", f"Type ERASE to confirm destructive install to {target}:")
        if not ok or typed.strip() != "ERASE":
            self.status.setText("Install cancelled.")
            return
        try:
            cmd = build_install_command(target, hostname, user, timezone, password)
        except Exception as exc:
            QtWidgets.QMessageBox.critical(self, APP_NAME, str(exc))
            return
        shown = list(cmd)
        if password:
            for idx, item in enumerate(shown[:-1]):
                if item == "--user-password":
                    shown[idx + 1] = "***"
        self.append_log("\n$ " + " ".join(shown))
        self.start_process(cmd, f"Installing CRIXA to {target}...")

    def start_process(self, cmd: list[str], message: str) -> None:
        if self.proc is not None:
            return
        self.output_buffer = ""
        self.progress.setValue(0)
        self.set_busy(True, message)
        self.proc = QtCore.QProcess(self)
        self.proc.setProgram(cmd[0])
        self.proc.setArguments(cmd[1:])
        self.proc.readyReadStandardOutput.connect(self.read_stdout)
        self.proc.readyReadStandardError.connect(self.read_stderr)
        self.proc.finished.connect(self.process_finished)
        self.proc.start()
        if not self.proc.waitForStarted(1500):
            self.append_log(f"Failed to start: {cmd[0]}")
            self.status.setText("Failed to start operation.")
            self.proc = None
            self.set_busy(False)

    def read_stdout(self) -> None:
        if self.proc is None:
            return
        self.output_buffer += bytes(self.proc.readAllStandardOutput()).decode(errors="replace")
        while "\n" in self.output_buffer:
            line, self.output_buffer = self.output_buffer.split("\n", 1)
            self.handle_output_line(line.strip())

    def read_stderr(self) -> None:
        if self.proc is None:
            return
        text = bytes(self.proc.readAllStandardError()).decode(errors="replace").strip()
        if text:
            self.append_log(text)

    def handle_output_line(self, line: str) -> None:
        if not line:
            return
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            self.append_log(line)
            return
        event = str(payload.get("event", "log"))
        message = str(payload.get("message", ""))
        if event == "stage":
            self.progress.setValue(int(payload.get("progress", self.progress.value())))
            self.status.setText(message)
        elif event == "error":
            self.status.setText(message)
        elif event == "plan":
            parts = payload.get("partitions", [])
            self.append_log("Install plan:")
            for part in (parts if isinstance(parts, list) else []):
                self.append_log(f"  {part.get('path', '')}: {part.get('role', '')} {part.get('size', '')}")
            return
        if message:
            self.append_log(message)

    def process_finished(self, code: int, _status: QtCore.QProcess.ExitStatus) -> None:
        if self.output_buffer.strip():
            self.handle_output_line(self.output_buffer.strip())
        self.proc = None
        self.set_busy(False)
        if code == 0:
            if self.progress.value() < 100:
                self.progress.setValue(100)
            self.status.setText("Operation completed.")
        else:
            self.status.setText(f"Operation failed with exit code {code}.")

    def open_log(self) -> None:
        path = Path(DEFAULT_LOG)
        if path.exists():
            opener = shutil.which("crixa-files") or shutil.which("xdg-open")
            if opener:
                subprocess.Popen([opener, str(path.parent)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return
        QtWidgets.QMessageBox.information(self, APP_NAME, "Installer log has not been created yet.")

    def open_terminal_mode(self) -> None:
        terminals = [
            ["konsole", "-e", "crixa-installer", "--tui"],
            ["alacritty", "-e", "crixa-installer", "--tui"],
            ["xterm", "-e", "crixa-installer", "--tui"],
        ]
        for cmd in terminals:
            if shutil.which(cmd[0]):
                subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return
        QtWidgets.QMessageBox.information(self, APP_NAME, "No graphical terminal was found. Run: crixa-installer --tui")


def dialog_binary() -> str:
    return shutil.which("whiptail") or shutil.which("dialog") or ""


def run_dialog(args: list[str]) -> tuple[int, str]:
    exe = dialog_binary()
    if not exe:
        return 127, ""
    result = subprocess.run([exe] + args, capture_output=True, text=True, check=False)
    return result.returncode, (result.stdout or result.stderr).strip()


def choose_disk_tui(disks: list[DiskInfo]) -> DiskInfo | None:
    if not disks:
        print("No installable disks detected.")
        return None
    exe = dialog_binary()
    if exe:
        menu: list[str] = ["--title", "Dockyard", "--menu", "Choose a target disk. The selected disk will be erased.", "20", "86", "10"]
        for disk in disks:
            menu.extend([disk.path, f"{disk.size}  {disk.model}  {disk.kind}"])
        code, value = run_dialog(menu)
        if code != 0:
            return None
        return next((disk for disk in disks if disk.path == value), None)
    for idx, disk in enumerate(disks, start=1):
        print(f"{idx}. {disk.path}  {disk.size}  {disk.model}  {disk.kind}")
    raw = input("Target disk number: ").strip()
    try:
        idx = int(raw) - 1
        return disks[idx]
    except Exception:
        return None


def prompt_tui(label: str, default: str = "", password: bool = False) -> str:
    exe = dialog_binary()
    if exe:
        flag = "--passwordbox" if password else "--inputbox"
        code, value = run_dialog(["--title", "Dockyard", flag, label, "10", "70", default])
        if code != 0:
            raise RuntimeError("cancelled")
        return value or default
    if password:
        import getpass

        return getpass.getpass(label + ": ")
    raw = input(f"{label} [{default}]: ").strip()
    return raw or default


def confirm_tui(target: str) -> bool:
    exe = dialog_binary()
    if exe:
        code, _ = run_dialog(["--title", "Confirm Install", "--yesno", f"ERASE {target} and install CRIXA OS?", "10", "72"])
        return code == 0
    return input(f"Type ERASE to install to {target}: ").strip() == "ERASE"


def run_tui(args: argparse.Namespace) -> int:
    if args.self_test:
        return run_self_test(tui=True)
    try:
        disks = probe_disks()
        disk = choose_disk_tui(disks)
        if disk is None:
            return 1
        hostname = prompt_tui("Hostname", "crixa-os")
        user = prompt_tui("Primary user", "crixa")
        timezone = prompt_tui("Timezone", "UTC")
        password = prompt_tui("Password (blank allowed)", "", password=True)
        dry_run_first = True
        if dialog_binary():
            code, _ = run_dialog(["--title", "Dry Run", "--yesno", "Run a non-destructive dry-run preview first?", "9", "68"])
            dry_run_first = code == 0
        if dry_run_first:
            subprocess.run(build_dry_run_command(disk.path, hostname, user, timezone, password), check=False)
        if not confirm_tui(disk.path):
            print("Install cancelled.")
            return 1
        cmd = build_install_command(disk.path, hostname, user, timezone, password)
        return subprocess.call(cmd)
    except Exception as exc:
        print(f"Dockyard TTY failed: {exc}", file=sys.stderr)
        return 1


def run_self_test(tui: bool = False) -> int:
    checks: list[tuple[str, bool, str]] = []
    checks.append(("backend", INSTALLER_BIN.exists() or shutil.which("crixa-install") is not None, str(INSTALLER_BIN)))
    checks.append(("probe", shutil.which("lsblk") is not None, "lsblk is available"))
    if tui:
        checks.append(("terminal UI", bool(dialog_binary()), "whiptail/dialog available"))
    else:
        checks.append(("PySide2", QT_IMPORT_ERROR is None, str(QT_IMPORT_ERROR or "available")))
    checks.append(("privileged helper", HELPER_BIN.exists(), str(HELPER_BIN)))
    checks.append(("pkexec", shutil.which("pkexec") is not None or os.geteuid() == 0, "pkexec available or already root"))

    ok = True
    for name, passed, detail in checks:
        required = name not in {"terminal UI", "pkexec"}
        ok = ok and (passed or not required)
        state = "ok" if passed else ("warn" if not required else "fail")
        print(f"{state}: {name} - {detail}")
    try:
        disks = probe_disks()
        print(f"ok: disk probe - {len(disks)} candidate disk(s)")
    except Exception as exc:
        ok = False
        print(f"fail: disk probe - {exc}")
    return 0 if ok else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="CRIXA Dockyard installer")
    parser.add_argument("--self-test", action="store_true", help="validate Dockyard dependencies and backend access")
    parser.add_argument("--tui", action="store_true", help="run terminal/TTY installer")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    if args.tui:
        return run_tui(args)
    if args.self_test:
        return run_self_test(tui=False)
    if QT_IMPORT_ERROR is not None:
        print(f"{APP_NAME} requires python3-pyside2.qtwidgets: {QT_IMPORT_ERROR}", file=sys.stderr)
        return 1
    app = QtWidgets.QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setWindowIcon(QtGui.QIcon.fromTheme("crixa-installer"))
    app.setStyleSheet(stylesheet())
    window = DockyardWindow()
    window.show()
    return int(app.exec_())


if __name__ == "__main__":
    raise SystemExit(main())
