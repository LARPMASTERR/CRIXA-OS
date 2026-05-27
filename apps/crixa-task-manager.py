#!/usr/bin/env python3
from __future__ import annotations

import argparse
import getpass
import html
import json
import os
import platform
import pwd
import shutil
import signal
import socket
import subprocess
import sys
import termios
import time
import tty
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

try:
    import psutil

    PSUTIL_IMPORT_ERROR: Exception | None = None
except Exception as exc:  # pragma: no cover - depends on host image
    psutil = None  # type: ignore[assignment]
    PSUTIL_IMPORT_ERROR = exc

try:
    from PySide2 import QtCore, QtGui, QtWidgets

    QT_IMPORT_ERROR: Exception | None = None
except Exception as exc:  # pragma: no cover - exercised on minimal hosts
    QtCore = QtGui = QtWidgets = None  # type: ignore[assignment]
    QT_IMPORT_ERROR = exc


APP_NAME = "Pulse"
HELPER_PATH = Path("/usr/lib/crixa-task-manager/crixa-task-manager-helper.py")
DEV_ROOT = Path(__file__).resolve().parents[1] if Path(__file__).resolve().parent.name == "apps" else None
DEV_HELPER_PATH = DEV_ROOT / "apps" / "crixa-task-manager-helper.py" if DEV_ROOT else None
SYSTEMMONITOR_CANDIDATES = ("systemmonitor", "plasma-systemmonitor")


@dataclass(slots=True)
class ProcessRow:
    pid: int
    name: str
    user: str
    cpu: float
    mem: float
    rss: int
    status: str
    threads: int
    uptime: str
    nice: int
    command: str
    owned: bool
    system_owned: bool


def clear_screen() -> None:
    sys.stdout.write("\033[H\033[2J")
    sys.stdout.flush()


def human_bytes(value: float) -> str:
    units = ["B", "KB", "MB", "GB", "TB", "PB"]
    idx = 0
    while value >= 1024.0 and idx < len(units) - 1:
        value /= 1024.0
        idx += 1
    return f"{value:,.1f} {units[idx]}"


def human_rate(value: float) -> str:
    return f"{human_bytes(value)}/s"


def short_duration(seconds: float) -> str:
    seconds = max(0, int(seconds))
    days, rem = divmod(seconds, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, secs = divmod(rem, 60)
    if days:
        return f"{days}d {hours}h"
    if hours:
        return f"{hours}h {minutes}m"
    if minutes:
        return f"{minutes}m {secs}s"
    return f"{secs}s"


def read_cpu_totals() -> tuple[int, int]:
    with open("/proc/stat", "r", encoding="utf-8") as handle:
        parts = handle.readline().split()[1:]
    vals = [int(v) for v in parts]
    total = sum(vals)
    idle = vals[3] + vals[4]
    return total, idle


def read_meminfo() -> dict[str, int]:
    info: dict[str, int] = {}
    with open("/proc/meminfo", "r", encoding="utf-8") as handle:
        for line in handle:
            key, value = line.split(":", 1)
            info[key] = int(value.strip().split()[0])
    return info


def read_net_bytes() -> tuple[int, int]:
    rx_total = 0
    tx_total = 0
    with open("/proc/net/dev", "r", encoding="utf-8") as handle:
        lines = handle.readlines()[2:]
    for line in lines:
        iface, rest = line.split(":", 1)
        if iface.strip() == "lo":
            continue
        cols = rest.split()
        rx_total += int(cols[0])
        tx_total += int(cols[8])
    return rx_total, tx_total


def read_uptime() -> str:
    if psutil is not None:
        return short_duration(time.time() - psutil.boot_time())
    with open("/proc/uptime", "r", encoding="utf-8") as handle:
        seconds = int(float(handle.readline().split()[0]))
    return str(timedelta(seconds=seconds))


def cpu_model() -> str:
    try:
        with open("/proc/cpuinfo", "r", encoding="utf-8") as handle:
            for line in handle:
                if line.startswith("model name"):
                    return line.split(":", 1)[1].strip()
    except Exception:
        pass
    return platform.processor() or "Unknown CPU"


def read_chassis_info() -> list[str]:
    cpu_count = psutil.cpu_count(logical=True) if psutil is not None else os.cpu_count()
    return [
        f"Host: {socket.gethostname()}",
        f"Kernel: {platform.release()}",
        f"CPU: {cpu_model()}",
        f"vCPUs: {cpu_count or 0}",
    ]


def process_rows(limit: int = 240, sort_mode: str = "cpu", query: str = "") -> list[ProcessRow]:
    if psutil is None:
        return process_rows_ps(limit=limit, sort_mode=sort_mode, query=query)
    rows: list[ProcessRow] = []
    current_user = getpass.getuser()
    now = time.time()
    attrs = ["pid", "name", "username", "cpu_percent", "memory_percent", "memory_info", "status", "num_threads", "create_time", "nice", "cmdline"]
    for proc in psutil.process_iter(attrs=attrs):
        try:
            info = proc.info
            pid = int(info.get("pid") or proc.pid)
            name = str(info.get("name") or "")
            user = str(info.get("username") or "")
            cmdline = info.get("cmdline") or []
            command = " ".join(cmdline) if isinstance(cmdline, list) else str(cmdline or "")
            haystack = f"{pid} {name} {user} {command}".lower()
            if query and query.lower() not in haystack:
                continue
            rss = getattr(info.get("memory_info"), "rss", 0) or 0
            create_time = float(info.get("create_time") or now)
            rows.append(
                ProcessRow(
                    pid=pid,
                    name=name or command[:32] or str(pid),
                    user=user,
                    cpu=float(info.get("cpu_percent") or 0.0),
                    mem=float(info.get("memory_percent") or 0.0),
                    rss=int(rss),
                    status=str(info.get("status") or ""),
                    threads=int(info.get("num_threads") or 0),
                    uptime=short_duration(now - create_time),
                    nice=int(info.get("nice") or 0),
                    command=command,
                    owned=user == current_user,
                    system_owned=user in ("root", "systemd-network", "systemd-timesync") or user.startswith("root"),
                )
            )
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue
        except Exception:
            continue
    key = {
        "mem": lambda row: row.mem,
        "rss": lambda row: row.rss,
        "pid": lambda row: -row.pid,
        "name": lambda row: row.name.lower(),
        "user": lambda row: row.user.lower(),
    }.get(sort_mode, lambda row: row.cpu)
    reverse = sort_mode not in ("name", "user", "pid")
    rows.sort(key=key, reverse=reverse)
    return rows[:limit]


def process_rows_ps(limit: int = 240, sort_mode: str = "cpu", query: str = "") -> list[ProcessRow]:
    sort_key = "-%cpu" if sort_mode == "cpu" else "-rss"
    cmd = ["ps", "-eo", "pid=,user=,comm=,%cpu=,%mem=,rss=,state=,nlwp=,ni=,etime=,args=", "--sort", sort_key]
    try:
        out = subprocess.check_output(cmd, text=True, stderr=subprocess.DEVNULL)
    except Exception:
        return []
    rows: list[ProcessRow] = []
    current_user = getpass.getuser()
    for line in out.splitlines():
        parts = line.split(None, 10)
        if len(parts) < 11:
            continue
        pid_s, user, name, cpu_s, mem_s, rss_s, state, threads_s, nice_s, uptime, command = parts
        haystack = f"{pid_s} {name} {user} {command}".lower()
        if query and query.lower() not in haystack:
            continue
        try:
            rows.append(
                ProcessRow(
                    pid=int(pid_s),
                    name=name,
                    user=user,
                    cpu=float(cpu_s),
                    mem=float(mem_s),
                    rss=int(rss_s) * 1024,
                    status=state,
                    threads=int(threads_s),
                    uptime=uptime,
                    nice=int(nice_s),
                    command=command,
                    owned=user == current_user,
                    system_owned=user == "root",
                )
            )
        except Exception:
            continue
        if len(rows) >= limit:
            break
    return rows


def read_top_processes(sort_mode: str, limit: int = 14) -> list[dict[str, str]]:
    rows = process_rows(limit=limit, sort_mode=sort_mode)
    return [
        {
            "pid": str(row.pid),
            "name": row.name[:24],
            "cpu": f"{row.cpu:.1f}",
            "mem": f"{row.mem:.1f}",
            "rss": human_bytes(row.rss),
            "state": row.status[:10],
        }
        for row in rows
    ]


def draw_bar(percent: float, width: int) -> str:
    percent = max(0.0, min(100.0, percent))
    filled = int((percent / 100.0) * width)
    return "[" + ("#" * filled) + ("-" * (width - filled)) + f"] {percent:5.1f}%"


def select_ready(fd: int, timeout: float) -> bool:
    import select

    ready, _, _ = select.select([fd], [], [], timeout)
    return bool(ready)


def run_tui() -> int:
    sort_mode = "cpu"
    net_prev = read_net_bytes()
    cpu_prev = read_cpu_totals()
    last_time = time.time()
    chassis_info = read_chassis_info()

    if not sys.stdin.isatty():
        print("Task manager TUI needs a terminal (TTY).", file=sys.stderr)
        return 1

    fd = sys.stdin.fileno()
    old_tty = termios.tcgetattr(fd)
    tty.setcbreak(fd)
    os.system("stty -echo")

    try:
        while True:
            now = time.time()
            dt = max(0.5, now - last_time)
            last_time = now

            cpu_now = read_cpu_totals()
            total_delta = cpu_now[0] - cpu_prev[0]
            idle_delta = cpu_now[1] - cpu_prev[1]
            cpu_prev = cpu_now
            cpu_usage = 0.0
            if total_delta > 0:
                cpu_usage = (1.0 - (idle_delta / total_delta)) * 100.0

            mem = psutil.virtual_memory() if psutil is not None else None
            swap = psutil.swap_memory() if psutil is not None else None
            if mem is not None:
                mem_used = int(mem.used)
                mem_total = int(mem.total)
                mem_usage = float(mem.percent)
            else:
                raw = read_meminfo()
                mem_total = raw.get("MemTotal", 1) * 1024
                mem_used = (raw.get("MemTotal", 0) - raw.get("MemAvailable", 0)) * 1024
                mem_usage = (mem_used / mem_total) * 100.0 if mem_total else 0.0
            if swap is not None:
                swap_used = int(swap.used)
                swap_total = int(swap.total)
                swap_usage = float(swap.percent)
            else:
                raw = read_meminfo()
                swap_total = raw.get("SwapTotal", 0) * 1024
                swap_used = (raw.get("SwapTotal", 0) - raw.get("SwapFree", 0)) * 1024
                swap_usage = (swap_used / swap_total) * 100.0 if swap_total else 0.0

            net_now = read_net_bytes()
            rx_rate = (net_now[0] - net_prev[0]) / dt
            tx_rate = (net_now[1] - net_prev[1]) / dt
            net_prev = net_now

            disk = shutil.disk_usage("/")
            disk_usage = ((disk.used / disk.total) * 100.0) if disk.total else 0.0

            clear_screen()
            width = shutil.get_terminal_size((120, 40)).columns
            bar_w = max(20, min(42, width - 30))

            print("Pulse")
            print("=" * min(width, 80))
            for line in chassis_info:
                print(line)
            print(f"Uptime: {read_uptime()}  |  Sort: {sort_mode.upper()}")
            print()
            print(f"CPU  {draw_bar(cpu_usage, bar_w)}")
            print(f"MEM  {draw_bar(mem_usage, bar_w)}  ({human_bytes(mem_used)} / {human_bytes(mem_total)})")
            print(f"SWAP {draw_bar(swap_usage, bar_w)}  ({human_bytes(swap_used)} / {human_bytes(swap_total)})")
            print(f"DISK {draw_bar(disk_usage, bar_w)}  ({human_bytes(disk.used)} / {human_bytes(disk.total)})")
            print(f"NET  RX {human_rate(rx_rate)}  TX {human_rate(tx_rate)}")
            print()
            print("PID     NAME                  CPU%   MEM%      RSS   STATE")
            print("-" * min(width, 80))
            rows = read_top_processes(sort_mode=sort_mode, limit=14)
            if not rows:
                print("  <unable to read process table>")
            for row in rows:
                print(
                    f"{row['pid']:>6}  {row['name']:<24}  {row['cpu']:>5}%  {row['mem']:>5}%  "
                    f"{row['rss']:>8}  {row['state']}"
                )
            print()
            print("[q] Quit   [s] Toggle CPU/MEM sort")
            sys.stdout.flush()

            end_time = time.time() + 1.0
            while time.time() < end_time:
                if select_ready(fd, timeout=0.10):
                    key = os.read(fd, 1).decode("utf-8", errors="ignore").lower()
                    if key == "q":
                        return 0
                    if key == "s":
                        sort_mode = "mem" if sort_mode == "cpu" else "cpu"
                        break
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_tty)
        os.system("stty echo")
        print()


def run_command(args: list[str], timeout: int = 4) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(args, capture_output=True, text=True, check=False, timeout=timeout)
    except Exception as exc:
        return subprocess.CompletedProcess(args, 127, "", str(exc))


def helper_path() -> Path:
    if HELPER_PATH.exists():
        return HELPER_PATH
    if DEV_HELPER_PATH is not None and DEV_HELPER_PATH.exists():
        return DEV_HELPER_PATH
    return HELPER_PATH


def helper_available() -> bool:
    path = helper_path()
    return path.exists() and (os.geteuid() == 0 or shutil.which("pkexec") is not None)


def launch_kde_systemmonitor(args: list[str]) -> int:
    for candidate in SYSTEMMONITOR_CANDIDATES:
        if shutil.which(candidate):
            os.execvp(candidate, [candidate, *args])
    print("KDE System Monitor is not installed.", file=sys.stderr)
    return 127


def self_test() -> int:
    failures: list[str] = []
    warnings: list[str] = []
    if QT_IMPORT_ERROR is not None:
        failures.append(f"PySide2 Qt Widgets import failed: {QT_IMPORT_ERROR}")
    if PSUTIL_IMPORT_ERROR is not None:
        failures.append(f"psutil import failed: {PSUTIL_IMPORT_ERROR}")
    for path in (Path("/proc/stat"), Path("/proc/meminfo"), Path("/proc/net/dev")):
        if not path.exists() or not os.access(path, os.R_OK):
            failures.append(f"Cannot read {path}")
    if not helper_path().exists():
        warnings.append(f"Privileged helper not installed: {helper_path()}")
    for tool in ("upower", "nvidia-smi", "sensors", "pkexec"):
        if shutil.which(tool) is None:
            warnings.append(f"Optional tool not available: {tool}")
    try:
        _ = process_rows(limit=3)
    except Exception as exc:
        failures.append(f"Process scan failed: {exc}")
    if failures:
        print("Pulse self-test failed:")
        for item in failures:
            print(f"- {item}")
        for item in warnings:
            print(f"warning: {item}")
        return 1
    print("Pulse self-test passed")
    qt_version = QtCore.qVersion() if QtCore is not None else "unavailable"
    print(f"Qt binding: PySide2 / Qt {qt_version}")
    print(f"psutil: {getattr(psutil, '__version__', 'unavailable')}")
    print(f"Helper: {helper_path()} ({'available' if helper_available() else 'not privileged-ready'})")
    for item in warnings:
        print(f"warning: {item}")
    return 0


if QT_IMPORT_ERROR is None:

    class HistoryGraph(QtWidgets.QWidget):
        def __init__(self, color: str = "#34c6b6", parent=None) -> None:
            super().__init__(parent)
            self.values: list[float] = []
            self.color = QtGui.QColor(color)
            self.setMinimumHeight(54)
            self.setMaximumHeight(72)

        def push(self, value: float) -> None:
            self.values.append(max(0.0, min(100.0, float(value))))
            self.values = self.values[-80:]
            self.update()

        def paintEvent(self, _event) -> None:  # noqa: N802
            painter = QtGui.QPainter(self)
            painter.setRenderHint(QtGui.QPainter.Antialiasing)
            rect = self.rect().adjusted(1, 1, -1, -1)
            painter.fillRect(rect, QtGui.QColor("#0c1014"))
            painter.setPen(QtGui.QPen(QtGui.QColor("#26323a"), 1))
            for i in range(1, 4):
                y = rect.top() + (rect.height() * i / 4)
                painter.drawLine(rect.left(), int(y), rect.right(), int(y))
            if len(self.values) < 2:
                return
            path = QtGui.QPainterPath()
            span = max(1, len(self.values) - 1)
            for index, value in enumerate(self.values):
                x = rect.left() + (rect.width() * index / span)
                y = rect.bottom() - (rect.height() * value / 100.0)
                if index == 0:
                    path.moveTo(x, y)
                else:
                    path.lineTo(x, y)
            painter.setPen(QtGui.QPen(self.color, 2))
            painter.drawPath(path)


    class MetricCard(QtWidgets.QFrame):
        def __init__(self, title: str, accent: str, parent=None) -> None:
            super().__init__(parent)
            self.setObjectName("MetricCard")
            self.title = QtWidgets.QLabel(title)
            self.title.setObjectName("CardTitle")
            self.value = QtWidgets.QLabel("0%")
            self.value.setObjectName("MetricValue")
            self.detail = QtWidgets.QLabel("")
            self.detail.setObjectName("CardMeta")
            self.detail.setWordWrap(True)
            self.graph = HistoryGraph(accent)
            layout = QtWidgets.QVBoxLayout(self)
            layout.setContentsMargins(14, 12, 14, 12)
            layout.setSpacing(7)
            layout.addWidget(self.title)
            layout.addWidget(self.value)
            layout.addWidget(self.detail)
            layout.addWidget(self.graph)

        def update_metric(self, percent: float, value: str, detail: str) -> None:
            self.value.setText(value)
            self.detail.setText(detail)
            self.graph.push(percent)


    class ProcessDetail(QtWidgets.QTextBrowser):
        def __init__(self, parent=None) -> None:
            super().__init__(parent)
            self.setObjectName("DetailText")
            self.setOpenExternalLinks(False)
            self.setMinimumHeight(160)

        def show_process(self, row: ProcessRow | None) -> None:
            if row is None:
                self.setHtml("<p>Select a process to inspect command, owner, and action state.</p>")
                return
            self.setHtml(
                f"""
                <h3>{html.escape(row.name)}</h3>
                <p><b>PID:</b> {row.pid}<br>
                <b>User:</b> {html.escape(row.user or 'unknown')}<br>
                <b>Status:</b> {html.escape(row.status)}<br>
                <b>Threads:</b> {row.threads}<br>
                <b>Uptime:</b> {row.uptime}<br>
                <b>Nice:</b> {row.nice}<br>
                <b>Memory:</b> {human_bytes(row.rss)} ({row.mem:.1f}%)</p>
                <p><b>Command</b><br>{html.escape(row.command)}</p>
                """
            )


    class PulseWindow(QtWidgets.QMainWindow):
        def __init__(self) -> None:
            super().__init__()
            self.setWindowTitle(APP_NAME)
            self.resize(1180, 760)
            self.setMinimumSize(1024, 680)
            self.net_prev = psutil.net_io_counters() if psutil is not None else None
            self.disk_prev = psutil.disk_io_counters() if psutil is not None else None
            self.last_tick = time.time()
            self.process_cache: dict[int, ProcessRow] = {}
            self.process_sort = "cpu"
            self.selected_pid: int | None = None
            self.hardware_tick = 0
            if psutil is not None:
                psutil.cpu_percent(interval=None, percpu=True)
                for proc in psutil.process_iter():
                    try:
                        proc.cpu_percent(interval=None)
                    except Exception:
                        pass
            self.build_ui()
            self.apply_style()
            self.refresh_all()
            self.timer = QtCore.QTimer(self)
            self.timer.timeout.connect(self.refresh_all)
            self.timer.start(1000)

        def build_ui(self) -> None:
            root = QtWidgets.QWidget()
            root.setObjectName("Root")
            self.setCentralWidget(root)
            layout = QtWidgets.QVBoxLayout(root)
            layout.setContentsMargins(20, 18, 20, 18)
            layout.setSpacing(12)

            header = QtWidgets.QHBoxLayout()
            title_box = QtWidgets.QVBoxLayout()
            title = QtWidgets.QLabel("Pulse")
            title.setObjectName("PageTitle")
            self.subtitle = QtWidgets.QLabel("Live system metrics and process control")
            self.subtitle.setObjectName("PageSubtitle")
            title_box.addWidget(title)
            title_box.addWidget(self.subtitle)
            header.addLayout(title_box, 1)
            self.status = QtWidgets.QLabel("Ready")
            self.status.setObjectName("Status")
            header.addWidget(self.status)
            layout.addLayout(header)

            self.tabs = QtWidgets.QTabWidget()
            self.tabs.setObjectName("Tabs")
            layout.addWidget(self.tabs, 1)

            self.build_overview_tab()
            self.build_processes_tab()
            self.build_performance_tab()
            self.build_hardware_tab()

        def build_overview_tab(self) -> None:
            tab = QtWidgets.QWidget()
            layout = QtWidgets.QVBoxLayout(tab)
            layout.setContentsMargins(12, 12, 12, 12)
            layout.setSpacing(12)
            cards = QtWidgets.QGridLayout()
            cards.setHorizontalSpacing(12)
            cards.setVerticalSpacing(12)
            self.cpu_card = MetricCard("CPU", "#34c6b6")
            self.mem_card = MetricCard("Memory", "#8fb7ff")
            self.disk_card = MetricCard("Disk", "#e5bd65")
            self.net_card = MetricCard("Network", "#e88d75")
            cards.addWidget(self.cpu_card, 0, 0)
            cards.addWidget(self.mem_card, 0, 1)
            cards.addWidget(self.disk_card, 1, 0)
            cards.addWidget(self.net_card, 1, 1)
            layout.addLayout(cards)

            lower = QtWidgets.QHBoxLayout()
            self.summary_panel = QtWidgets.QTextBrowser()
            self.summary_panel.setObjectName("DetailText")
            self.summary_panel.setMinimumHeight(180)
            lower.addWidget(self.summary_panel, 1)
            self.top_table = QtWidgets.QTableWidget(0, 5)
            self.top_table.setObjectName("ProcessTable")
            self.top_table.setHorizontalHeaderLabels(["PID", "Name", "CPU", "Memory", "User"])
            self.top_table.horizontalHeader().setStretchLastSection(True)
            self.top_table.verticalHeader().setVisible(False)
            self.top_table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
            self.top_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
            lower.addWidget(self.top_table, 2)
            layout.addLayout(lower, 1)
            self.tabs.addTab(tab, QtGui.QIcon.fromTheme("view-dashboard"), "Overview")

        def build_processes_tab(self) -> None:
            tab = QtWidgets.QWidget()
            layout = QtWidgets.QVBoxLayout(tab)
            layout.setContentsMargins(12, 12, 12, 12)
            layout.setSpacing(10)

            tools = QtWidgets.QHBoxLayout()
            self.search = QtWidgets.QLineEdit()
            self.search.setObjectName("SearchBox")
            self.search.setPlaceholderText("Filter by PID, name, user, or command")
            self.search.textChanged.connect(self.refresh_processes)
            self.sort_combo = QtWidgets.QComboBox()
            self.sort_combo.addItem("CPU", "cpu")
            self.sort_combo.addItem("Memory %", "mem")
            self.sort_combo.addItem("Resident Memory", "rss")
            self.sort_combo.addItem("Name", "name")
            self.sort_combo.addItem("User", "user")
            self.sort_combo.addItem("PID", "pid")
            self.sort_combo.currentIndexChanged.connect(self.on_sort_changed)
            tools.addWidget(self.search, 1)
            tools.addWidget(self.sort_combo)
            layout.addLayout(tools)

            self.process_table = QtWidgets.QTableWidget(0, 10)
            self.process_table.setObjectName("ProcessTable")
            self.process_table.setHorizontalHeaderLabels(["PID", "Name", "User", "CPU", "Mem", "RSS", "Status", "Threads", "Nice", "Uptime"])
            self.process_table.horizontalHeader().setStretchLastSection(True)
            self.process_table.verticalHeader().setVisible(False)
            self.process_table.setAlternatingRowColors(True)
            self.process_table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
            self.process_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
            self.process_table.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
            self.process_table.itemSelectionChanged.connect(self.on_process_selected)
            layout.addWidget(self.process_table, 1)

            actions = QtWidgets.QHBoxLayout()
            self.end_btn = QtWidgets.QPushButton(QtGui.QIcon.fromTheme("process-stop"), "End")
            self.kill_btn = QtWidgets.QPushButton(QtGui.QIcon.fromTheme("edit-delete"), "Force Kill")
            self.nice_btn = QtWidgets.QPushButton(QtGui.QIcon.fromTheme("preferences-system"), "Set Priority")
            self.refresh_btn = QtWidgets.QPushButton(QtGui.QIcon.fromTheme("view-refresh"), "Refresh")
            self.end_btn.clicked.connect(lambda: self.process_action("terminate"))
            self.kill_btn.clicked.connect(lambda: self.process_action("kill"))
            self.nice_btn.clicked.connect(self.renice_selected)
            self.refresh_btn.clicked.connect(self.refresh_all)
            actions.addWidget(self.end_btn)
            actions.addWidget(self.kill_btn)
            actions.addWidget(self.nice_btn)
            actions.addStretch(1)
            actions.addWidget(self.refresh_btn)
            layout.addLayout(actions)
            self.detail = ProcessDetail()
            layout.addWidget(self.detail)
            self.tabs.addTab(tab, QtGui.QIcon.fromTheme("utilities-system-monitor"), "Processes")

        def build_performance_tab(self) -> None:
            tab = QtWidgets.QWidget()
            layout = QtWidgets.QVBoxLayout(tab)
            layout.setContentsMargins(12, 12, 12, 12)
            splitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal)
            self.core_table = QtWidgets.QTableWidget(0, 2)
            self.core_table.setObjectName("ProcessTable")
            self.core_table.setHorizontalHeaderLabels(["Core", "Usage"])
            self.core_table.horizontalHeader().setStretchLastSection(True)
            self.core_table.verticalHeader().setVisible(False)
            self.io_panel = QtWidgets.QTextBrowser()
            self.io_panel.setObjectName("DetailText")
            splitter.addWidget(self.core_table)
            splitter.addWidget(self.io_panel)
            splitter.setSizes([420, 620])
            layout.addWidget(splitter, 1)
            self.tabs.addTab(tab, QtGui.QIcon.fromTheme("office-chart-line"), "Performance")

        def build_hardware_tab(self) -> None:
            tab = QtWidgets.QWidget()
            layout = QtWidgets.QVBoxLayout(tab)
            layout.setContentsMargins(12, 12, 12, 12)
            self.hardware_panel = QtWidgets.QTextBrowser()
            self.hardware_panel.setObjectName("DetailText")
            layout.addWidget(self.hardware_panel)
            self.tabs.addTab(tab, QtGui.QIcon.fromTheme("computer"), "Hardware")

        def apply_style(self) -> None:
            self.setStyleSheet(
                """
                QWidget#Root { background: #101316; color: #edf5f2; font-family: "IBM Plex Sans", "Inter", "Helvetica", sans-serif; font-size: 10.5pt; }
                QLabel#PageTitle { color: #f6fbf8; font-size: 27px; font-weight: 760; }
                QLabel#PageSubtitle, QLabel#CardMeta, QLabel#Status { color: #9aacaa; }
                QTabWidget#Tabs::pane { border: 1px solid #2b363f; background: #151b20; border-radius: 8px; }
                QTabBar::tab { background: #1b232a; color: #bfd0cc; padding: 9px 16px; border-top-left-radius: 7px; border-top-right-radius: 7px; margin-right: 3px; }
                QTabBar::tab:selected { background: #26333b; color: #ffffff; }
                QFrame#MetricCard { background: #182027; border: 1px solid #2c3842; border-radius: 8px; }
                QLabel#CardTitle { color: #c7d7d2; font-weight: 700; }
                QLabel#MetricValue { color: #f7fffb; font-size: 25px; font-weight: 780; }
                QLineEdit#SearchBox, QComboBox { background: #0c1014; border: 1px solid #303a43; border-radius: 7px; color: #edf5f2; padding: 8px 10px; }
                QLineEdit#SearchBox:focus, QComboBox:focus { border-color: #34c6b6; }
                QTableWidget#ProcessTable { background: #0c1014; alternate-background-color: #12181d; color: #edf5f2; border: 1px solid #303a43; border-radius: 8px; gridline-color: #253039; selection-background-color: #235e58; selection-color: white; }
                QHeaderView::section { background: #1d272e; color: #d7e5e0; border: 0; border-right: 1px solid #303a43; padding: 7px; font-weight: 700; }
                QTextBrowser#DetailText { background: #0c1014; border: 1px solid #303a43; border-radius: 8px; color: #d8e6e2; padding: 10px; }
                QPushButton { background: #25313a; border: 1px solid #3a4852; border-radius: 7px; color: #f2fbf7; padding: 8px 12px; font-weight: 650; }
                QPushButton:hover { background: #2b3a44; border-color: #4f6570; }
                QPushButton:disabled { color: #62716d; background: #171c20; border-color: #252d33; }
                """
            )

        def refresh_all(self) -> None:
            self.refresh_metrics()
            self.refresh_processes()
            self.hardware_tick += 1
            if self.hardware_tick == 1 or self.hardware_tick % 5 == 0:
                self.refresh_hardware()

        def refresh_metrics(self) -> None:
            now = time.time()
            dt = max(0.5, now - self.last_tick)
            self.last_tick = now
            if psutil is None:
                return
            cpu_percent = psutil.cpu_percent(interval=None)
            mem = psutil.virtual_memory()
            swap = psutil.swap_memory()
            disk = psutil.disk_usage("/")
            net = psutil.net_io_counters()
            rx_rate = tx_rate = 0.0
            if self.net_prev is not None:
                rx_rate = max(0.0, (net.bytes_recv - self.net_prev.bytes_recv) / dt)
                tx_rate = max(0.0, (net.bytes_sent - self.net_prev.bytes_sent) / dt)
            self.net_prev = net

            self.cpu_card.update_metric(cpu_percent, f"{cpu_percent:.0f}%", f"{psutil.cpu_count(logical=True) or 0} logical cores")
            self.mem_card.update_metric(mem.percent, f"{mem.percent:.0f}%", f"{human_bytes(mem.used)} used of {human_bytes(mem.total)}")
            self.disk_card.update_metric(disk.percent, f"{disk.percent:.0f}%", f"{human_bytes(disk.used)} used of {human_bytes(disk.total)}")
            net_percent = min(100.0, ((rx_rate + tx_rate) / (1024 * 1024 * 20)) * 100.0)
            self.net_card.update_metric(net_percent, human_rate(rx_rate + tx_rate), f"RX {human_rate(rx_rate)}  TX {human_rate(tx_rate)}")

            host = socket.gethostname()
            boot = datetime.fromtimestamp(psutil.boot_time()).strftime("%b %d, %Y %H:%M")
            self.subtitle.setText(f"{host} - {platform.release()} - Uptime {read_uptime()}")
            self.summary_panel.setHtml(
                f"""
                <h3>{host}</h3>
                <p><b>Kernel:</b> {platform.release()}<br>
                <b>Booted:</b> {boot}<br>
                <b>CPU:</b> {cpu_model()}<br>
                <b>Memory:</b> {human_bytes(mem.total)} total, {human_bytes(mem.available)} available<br>
                <b>Swap:</b> {human_bytes(swap.used)} used of {human_bytes(swap.total)}<br>
                <b>Processes:</b> {len(psutil.pids())}</p>
                """
            )
            per_core = psutil.cpu_percent(interval=None, percpu=True)
            self.core_table.setRowCount(len(per_core))
            for index, percent in enumerate(per_core):
                self.set_table_item(self.core_table, index, 0, f"CPU {index}")
                self.set_table_item(self.core_table, index, 1, f"{percent:.1f}%")
            self.refresh_io_panel(dt)

        def refresh_io_panel(self, dt: float) -> None:
            if psutil is None:
                return
            disk_io = psutil.disk_io_counters()
            read_rate = write_rate = 0.0
            if disk_io is not None and self.disk_prev is not None:
                read_rate = max(0.0, (disk_io.read_bytes - self.disk_prev.read_bytes) / dt)
                write_rate = max(0.0, (disk_io.write_bytes - self.disk_prev.write_bytes) / dt)
            self.disk_prev = disk_io
            parts = ["<h3>Storage</h3>"]
            for part in psutil.disk_partitions(all=False):
                try:
                    usage = psutil.disk_usage(part.mountpoint)
                    parts.append(f"<p><b>{part.mountpoint}</b> {part.device}<br>{human_bytes(usage.used)} / {human_bytes(usage.total)} ({usage.percent:.1f}%)</p>")
                except Exception:
                    continue
            parts.append(f"<h3>Disk IO</h3><p>Read {human_rate(read_rate)}<br>Write {human_rate(write_rate)}</p>")
            parts.append("<h3>Network Interfaces</h3>")
            for name, addrs in psutil.net_if_addrs().items():
                if name == "lo":
                    continue
                ips = [addr.address for addr in addrs if getattr(getattr(addr, "family", None), "name", "") in ("AF_INET", "AF_INET6")]
                parts.append(f"<p><b>{name}</b><br>{', '.join(ips) if ips else 'No address'}</p>")
            self.io_panel.setHtml("".join(parts))

        def refresh_processes(self) -> None:
            query = self.search.text() if hasattr(self, "search") else ""
            rows = process_rows(limit=400, sort_mode=self.process_sort, query=query)
            self.process_cache = {row.pid: row for row in rows}
            table = self.process_table
            selected = self.selected_pid
            table.blockSignals(True)
            table.setRowCount(len(rows))
            for index, row in enumerate(rows):
                values = [
                    str(row.pid),
                    row.name,
                    row.user,
                    f"{row.cpu:.1f}%",
                    f"{row.mem:.1f}%",
                    human_bytes(row.rss),
                    row.status,
                    str(row.threads),
                    str(row.nice),
                    row.uptime,
                ]
                for col, value in enumerate(values):
                    self.set_table_item(table, index, col, value, pid=row.pid)
            table.blockSignals(False)
            self.refresh_top_table(rows[:8])
            self.restore_selection(selected)
            self.update_action_state()

        def refresh_top_table(self, rows: list[ProcessRow]) -> None:
            self.top_table.setRowCount(len(rows))
            for index, row in enumerate(rows):
                values = [str(row.pid), row.name, f"{row.cpu:.1f}%", human_bytes(row.rss), row.user]
                for col, value in enumerate(values):
                    self.set_table_item(self.top_table, index, col, value)

        def set_table_item(self, table: QtWidgets.QTableWidget, row: int, col: int, value: str, pid: int | None = None) -> None:
            item = QtWidgets.QTableWidgetItem(value)
            if pid is not None:
                item.setData(QtCore.Qt.UserRole, pid)
            if col in (0, 3, 4, 5, 7, 8):
                item.setTextAlignment(QtCore.Qt.AlignCenter)
            table.setItem(row, col, item)

        def restore_selection(self, pid: int | None) -> None:
            if pid is None:
                self.detail.show_process(None)
                return
            for row in range(self.process_table.rowCount()):
                item = self.process_table.item(row, 0)
                if item and item.data(QtCore.Qt.UserRole) == pid:
                    self.process_table.selectRow(row)
                    return
            self.selected_pid = None
            self.detail.show_process(None)

        def on_sort_changed(self) -> None:
            self.process_sort = str(self.sort_combo.currentData() or "cpu")
            self.refresh_processes()

        def on_process_selected(self) -> None:
            rows = self.process_table.selectionModel().selectedRows()
            if not rows:
                self.selected_pid = None
                self.detail.show_process(None)
                self.update_action_state()
                return
            item = self.process_table.item(rows[0].row(), 0)
            self.selected_pid = int(item.data(QtCore.Qt.UserRole) or item.text()) if item else None
            self.detail.show_process(self.process_cache.get(self.selected_pid or -1))
            self.update_action_state()

        def update_action_state(self) -> None:
            row = self.process_cache.get(self.selected_pid or -1)
            enabled = row is not None and row.pid not in (0, 1, os.getpid())
            for button in (self.end_btn, self.kill_btn, self.nice_btn):
                button.setEnabled(enabled)

        def selected_process(self) -> ProcessRow | None:
            return self.process_cache.get(self.selected_pid or -1)

        def process_action(self, action: str) -> None:
            row = self.selected_process()
            if row is None:
                return
            label = "force kill" if action == "kill" else "end"
            if QtWidgets.QMessageBox.question(self, "Confirm Process Action", f"{label.title()} {row.name} (PID {row.pid})?") != QtWidgets.QMessageBox.Yes:
                return
            ok, message = self.run_process_action(row, action)
            self.set_status(message, error=not ok)
            self.refresh_processes()

        def renice_selected(self) -> None:
            row = self.selected_process()
            if row is None:
                return
            value, ok = QtWidgets.QInputDialog.getInt(self, "Set Priority", "Nice value (-20 highest, 19 lowest)", row.nice, -20, 19, 1)
            if not ok:
                return
            if QtWidgets.QMessageBox.question(self, "Confirm Priority Change", f"Set PID {row.pid} nice value to {value}?") != QtWidgets.QMessageBox.Yes:
                return
            ok, message = self.run_process_action(row, "renice", value)
            self.set_status(message, error=not ok)
            self.refresh_processes()

        def run_process_action(self, row: ProcessRow, action: str, value: int | None = None) -> tuple[bool, str]:
            needs_privilege = not row.owned
            if not needs_privilege and psutil is not None:
                try:
                    proc = psutil.Process(row.pid)
                    if action == "terminate":
                        proc.terminate()
                        return True, f"Sent terminate to PID {row.pid}"
                    if action == "kill":
                        proc.kill()
                        return True, f"Sent kill to PID {row.pid}"
                    if action == "renice" and value is not None:
                        proc.nice(value)
                        return True, f"Set PID {row.pid} nice value to {value}"
                except Exception as exc:
                    if helper_available():
                        return self.run_privileged_action(row.pid, action, value)
                    return False, str(exc)
            return self.run_privileged_action(row.pid, action, value)

        def run_privileged_action(self, pid: int, action: str, value: int | None) -> tuple[bool, str]:
            path = helper_path()
            if not path.exists():
                return False, "Privileged helper is not installed"
            payload = {"pid": pid, "action": action}
            if value is not None:
                payload["value"] = value
            command = [str(path)]
            if os.geteuid() != 0:
                pkexec = shutil.which("pkexec")
                if not pkexec:
                    return False, "pkexec is required for privileged process actions"
                command = [pkexec, str(path)]
            try:
                result = subprocess.run(command, input=json.dumps(payload), capture_output=True, text=True, check=False, timeout=30)
            except Exception as exc:
                return False, str(exc)
            text = (result.stdout or "").strip()
            err = (result.stderr or "").strip()
            try:
                response = json.loads(text or "{}")
            except json.JSONDecodeError:
                response = {"ok": result.returncode == 0, "message": text or err}
            ok = result.returncode == 0 and bool(response.get("ok", False))
            return ok, str(response.get("message") or response.get("error") or err or text or "process action complete")

        def set_status(self, message: str, error: bool = False) -> None:
            self.status.setText(message)
            self.status.setStyleSheet("color: #f08f79;" if error else "color: #9aacaa;")

        def refresh_hardware(self) -> None:
            parts = [
                "<h3>System</h3>",
                f"<p><b>Host:</b> {socket.gethostname()}<br><b>Kernel:</b> {platform.release()}<br><b>Machine:</b> {platform.machine()}<br><b>CPU:</b> {cpu_model()}</p>",
            ]
            parts.append(self.collect_upower())
            parts.append(self.collect_gpu())
            parts.append(self.collect_sensors())
            self.hardware_panel.setHtml("".join(parts))

        def collect_upower(self) -> str:
            if shutil.which("upower") is None:
                return "<h3>Power</h3><p>Not available.</p>"
            result = run_command(["upower", "-e"])
            devices = [line.strip() for line in result.stdout.splitlines() if line.strip()]
            batteries = [dev for dev in devices if "battery" in dev.lower()]
            if not batteries:
                return "<h3>Power</h3><p>No battery detected.</p>"
            chunks = ["<h3>Power</h3>"]
            for dev in batteries[:2]:
                detail = run_command(["upower", "-i", dev]).stdout
                fields = []
                for line in detail.splitlines():
                    stripped = line.strip()
                    if stripped.startswith(("state:", "percentage:", "time to", "energy:", "energy-full:", "capacity:")):
                        fields.append(stripped)
                chunks.append(f"<p><b>{dev.rsplit('/', 1)[-1]}</b><br>{'<br>'.join(fields) if fields else 'No detail available'}</p>")
            return "".join(chunks)

        def collect_gpu(self) -> str:
            if shutil.which("nvidia-smi") is None:
                return "<h3>GPU</h3><p>Not available.</p>"
            result = run_command(
                [
                    "nvidia-smi",
                    "--query-gpu=name,utilization.gpu,memory.used,memory.total,temperature.gpu",
                    "--format=csv,noheader,nounits",
                ]
            )
            if result.returncode != 0 or not result.stdout.strip():
                return "<h3>GPU</h3><p>Not available.</p>"
            rows = []
            for line in result.stdout.splitlines():
                parts = [part.strip() for part in line.split(",")]
                if len(parts) >= 5:
                    rows.append(f"<p><b>{parts[0]}</b><br>Usage {parts[1]}% - Memory {parts[2]} / {parts[3]} MiB - Temp {parts[4]} C</p>")
            return "<h3>GPU</h3>" + ("".join(rows) if rows else "<p>Not available.</p>")

        def collect_sensors(self) -> str:
            if shutil.which("sensors") is None:
                return "<h3>Thermals</h3><p>Not available.</p>"
            result = run_command(["sensors"])
            if result.returncode != 0 or not result.stdout.strip():
                return "<h3>Thermals</h3><p>Not available.</p>"
            lines = []
            for line in result.stdout.splitlines():
                if any(token in line.lower() for token in ("temp", "fan", "package id", "edge", "junction")):
                    lines.append(line.strip())
            return "<h3>Thermals</h3><p>" + ("<br>".join(lines[:24]) if lines else "No sensor detail available.") + "</p>"


def spawn_terminal_tui() -> bool:
    script = "/usr/local/bin/crixa-task-manager.py"
    if not Path(script).exists() and DEV_ROOT is not None:
        script = str(DEV_ROOT / "apps" / "crixa-task-manager.py")
    candidates = [
        ["xterm", "-fa", "DejaVu Sans Mono", "-fs", "10", "-bg", "#0b1220", "-fg", "#dbeafe", "-title", "Pulse", "-e", "python3", script, "--tui"],
        ["alacritty", "--title", "Pulse", "-e", "python3", script, "--tui"],
        ["konsole", "--new-tab", "-p", "tabtitle=Pulse", "-e", "python3", script, "--tui"],
    ]
    for cmd in candidates:
        if shutil.which(cmd[0]):
            subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return True
    return False


def run_gui() -> int:
    if QT_IMPORT_ERROR is not None:
        print(f"Pulse requires python3-pyside2.qtwidgets: {QT_IMPORT_ERROR}", file=sys.stderr)
        return 1
    if PSUTIL_IMPORT_ERROR is not None:
        print(f"Pulse requires python3-psutil: {PSUTIL_IMPORT_ERROR}", file=sys.stderr)
        return 1
    app = QtWidgets.QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    QtGui.QIcon.setThemeName("CRIXA-Depth")
    if not QtGui.QIcon.hasThemeIcon("utilities-system-monitor"):
        QtGui.QIcon.setThemeName("hicolor")
    window = PulseWindow()
    window.show()
    return int(app.exec_())


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Pulse")
    parser.add_argument("--tui", action="store_true", help="force terminal mode")
    parser.add_argument("--self-test", action="store_true", help="validate runtime without opening the UI")
    parser.add_argument("--kde-systemmonitor", action="store_true", help="open KDE System Monitor instead of Pulse")
    parser.add_argument("passthrough", nargs=argparse.REMAINDER)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.self_test:
        return self_test()
    if args.kde_systemmonitor:
        return launch_kde_systemmonitor(args.passthrough)
    if args.tui:
        return run_tui()

    display_ready = bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))
    if display_ready:
        result = run_gui()
        if result == 0:
            return 0
    if sys.stdin.isatty():
        return run_tui()
    if display_ready and spawn_terminal_tui():
        return 0
    print("Unable to start Pulse.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
