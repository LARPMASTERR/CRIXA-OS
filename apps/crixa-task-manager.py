#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import platform
import shutil
import socket
import subprocess
import sys
import termios
import time
import tty
from datetime import timedelta

try:
    import tkinter as tk
    from tkinter import ttk
except Exception:
    tk = None
    ttk = None


def clear_screen() -> None:
    sys.stdout.write("\033[H\033[2J")
    sys.stdout.flush()


def read_cpu_totals() -> tuple[int, int]:
    with open("/proc/stat", "r", encoding="utf-8") as f:
        parts = f.readline().split()[1:]
    vals = [int(v) for v in parts]
    total = sum(vals)
    idle = vals[3] + vals[4]
    return total, idle


def read_meminfo() -> dict[str, int]:
    info: dict[str, int] = {}
    with open("/proc/meminfo", "r", encoding="utf-8") as f:
        for line in f:
            key, value = line.split(":", 1)
            info[key] = int(value.strip().split()[0])
    return info


def read_net_bytes() -> tuple[int, int]:
    rx_total = 0
    tx_total = 0
    with open("/proc/net/dev", "r", encoding="utf-8") as f:
        lines = f.readlines()[2:]
    for line in lines:
        iface, rest = line.split(":", 1)
        iface = iface.strip()
        if iface == "lo":
            continue
        cols = rest.split()
        rx_total += int(cols[0])
        tx_total += int(cols[8])
    return rx_total, tx_total


def human_bytes(value: float) -> str:
    units = ["B", "KB", "MB", "GB", "TB"]
    idx = 0
    while value >= 1024.0 and idx < len(units) - 1:
        value /= 1024.0
        idx += 1
    return f"{value:,.1f} {units[idx]}"


def read_uptime() -> str:
    with open("/proc/uptime", "r", encoding="utf-8") as f:
        seconds = int(float(f.readline().split()[0]))
    return str(timedelta(seconds=seconds))


def read_chassis_info() -> list[str]:
    lines: list[str] = []
    cpu_model = ""
    cpu_cores = 0
    with open("/proc/cpuinfo", "r", encoding="utf-8") as f:
        for line in f:
            if line.startswith("model name") and not cpu_model:
                cpu_model = line.split(":", 1)[1].strip()
            if line.startswith("processor"):
                cpu_cores += 1
    lines.append(f"Host: {socket.gethostname()}")
    lines.append(f"Kernel: {platform.release()}")
    lines.append(f"CPU: {cpu_model}")
    lines.append(f"vCPUs: {cpu_cores}")
    return lines


def read_top_processes(sort_mode: str, limit: int = 14) -> list[dict[str, str]]:
    sort_key = "-%cpu" if sort_mode == "cpu" else "-rss"
    cmd = ["ps", "-eo", "pid=,comm=,%cpu=,%mem=,rss=,state=", "--sort", sort_key]
    try:
        out = subprocess.check_output(cmd, text=True, stderr=subprocess.DEVNULL)
    except Exception:
        return []

    rows: list[dict[str, str]] = []
    for line in out.splitlines()[:limit]:
        parts = line.split(None, 5)
        if len(parts) < 6:
            continue
        pid, name, cpu, mem, rss, state = parts
        rss_mb = int(rss) / 1024.0
        rows.append(
            {
                "pid": pid,
                "name": name[:24],
                "cpu": cpu,
                "mem": mem,
                "rss": f"{rss_mb:.1f}M",
                "state": state,
            }
        )
    return rows


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

            mem = read_meminfo()
            mem_total = mem.get("MemTotal", 1) * 1024
            mem_used = (mem.get("MemTotal", 0) - mem.get("MemAvailable", 0)) * 1024
            mem_usage = (mem_used / mem_total) * 100.0 if mem_total else 0.0
            swap_total = mem.get("SwapTotal", 0) * 1024
            swap_used = (mem.get("SwapTotal", 0) - mem.get("SwapFree", 0)) * 1024
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

            print("CRIXA Task Manager")
            print("=" * min(width, 80))
            for line in chassis_info:
                print(line)
            print(f"Uptime: {read_uptime()}  |  Sort: {sort_mode.upper()}")
            print()
            print(f"CPU  {draw_bar(cpu_usage, bar_w)}")
            print(f"MEM  {draw_bar(mem_usage, bar_w)}  ({human_bytes(mem_used)} / {human_bytes(mem_total)})")
            print(f"SWAP {draw_bar(swap_usage, bar_w)}  ({human_bytes(swap_used)} / {human_bytes(swap_total)})")
            print(f"DISK {draw_bar(disk_usage, bar_w)}  ({human_bytes(disk.used)} / {human_bytes(disk.total)})")
            print(f"NET  RX {human_bytes(rx_rate)}/s  TX {human_bytes(tx_rate)}/s")
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


class TaskManagerGUI(tk.Tk):  # type: ignore[misc]
    def __init__(self) -> None:
        super().__init__()
        self.title("CRIXA Task Manager")
        self.geometry("980x640")
        self.minsize(840, 520)
        self.configure(bg="#081326")

        self.sort_mode = "cpu"
        self.cpu_prev = read_cpu_totals()
        self.net_prev = read_net_bytes()
        self.last_time = time.time()

        self._build_ui()
        # Ensure the window is visible even when launched while another app has focus.
        self.after(80, self._raise_to_front)
        self._tick()

    def _raise_to_front(self) -> None:
        try:
            self.deiconify()
            self.lift()
            self.attributes("-topmost", True)
            self.focus_force()
            self.after(220, lambda: self.attributes("-topmost", False))
        except Exception:
            pass

    def _build_ui(self) -> None:
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        style.configure(".", background="#081326", foreground="#dbeafe", font=("DejaVu Sans", 10))
        style.configure("Card.TLabelframe", background="#10213b", foreground="#dbeafe")
        style.configure("Card.TLabelframe.Label", background="#10213b", foreground="#dbeafe")
        style.configure("TLabel", background="#081326", foreground="#dbeafe")
        style.configure("Muted.TLabel", background="#081326", foreground="#9db6da")
        style.configure("TButton", background="#1a3158", foreground="#dbeafe", padding=(10, 6))

        root = ttk.Frame(self)
        root.pack(fill="both", expand=True, padx=12, pady=10)
        root.columnconfigure(0, weight=1)
        root.rowconfigure(2, weight=1)

        header = ttk.Frame(root)
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(0, weight=1)
        ttk.Label(header, text="CRIXA Task Manager", font=("DejaVu Sans", 15, "bold")).grid(row=0, column=0, sticky="w")
        self.subtitle = ttk.Label(header, style="Muted.TLabel")
        self.subtitle.grid(row=1, column=0, sticky="w", pady=(2, 0))
        self.sort_btn = ttk.Button(header, text="Sort: CPU", command=self.toggle_sort)
        self.sort_btn.grid(row=0, column=1, rowspan=2, sticky="e")

        metrics = ttk.LabelFrame(root, text="System", style="Card.TLabelframe")
        metrics.grid(row=1, column=0, sticky="ew", pady=(10, 10))
        metrics.columnconfigure(1, weight=1)

        self.cpu_label = ttk.Label(metrics, text="CPU")
        self.cpu_label.grid(row=0, column=0, sticky="w", padx=10, pady=6)
        self.cpu_bar = ttk.Progressbar(metrics, maximum=100)
        self.cpu_bar.grid(row=0, column=1, sticky="ew", padx=10, pady=6)
        self.cpu_val = ttk.Label(metrics, text="0.0%")
        self.cpu_val.grid(row=0, column=2, sticky="e", padx=10, pady=6)

        self.mem_label = ttk.Label(metrics, text="Memory")
        self.mem_label.grid(row=1, column=0, sticky="w", padx=10, pady=6)
        self.mem_bar = ttk.Progressbar(metrics, maximum=100)
        self.mem_bar.grid(row=1, column=1, sticky="ew", padx=10, pady=6)
        self.mem_val = ttk.Label(metrics, text="0.0%")
        self.mem_val.grid(row=1, column=2, sticky="e", padx=10, pady=6)

        self.swap_label = ttk.Label(metrics, text="Swap")
        self.swap_label.grid(row=2, column=0, sticky="w", padx=10, pady=6)
        self.swap_bar = ttk.Progressbar(metrics, maximum=100)
        self.swap_bar.grid(row=2, column=1, sticky="ew", padx=10, pady=6)
        self.swap_val = ttk.Label(metrics, text="0.0%")
        self.swap_val.grid(row=2, column=2, sticky="e", padx=10, pady=6)

        self.disk_label = ttk.Label(metrics, text="Disk /")
        self.disk_label.grid(row=3, column=0, sticky="w", padx=10, pady=6)
        self.disk_bar = ttk.Progressbar(metrics, maximum=100)
        self.disk_bar.grid(row=3, column=1, sticky="ew", padx=10, pady=6)
        self.disk_val = ttk.Label(metrics, text="0.0%")
        self.disk_val.grid(row=3, column=2, sticky="e", padx=10, pady=6)

        self.net_label = ttk.Label(metrics, style="Muted.TLabel", text="NET")
        self.net_label.grid(row=4, column=0, columnspan=3, sticky="w", padx=10, pady=(2, 8))

        procs = ttk.LabelFrame(root, text="Processes", style="Card.TLabelframe")
        procs.grid(row=2, column=0, sticky="nsew")
        procs.columnconfigure(0, weight=1)
        procs.rowconfigure(0, weight=1)

        cols = ("pid", "name", "cpu", "mem", "rss", "state")
        self.tree = ttk.Treeview(procs, columns=cols, show="headings", height=15)
        for col, width in (
            ("pid", 70),
            ("name", 270),
            ("cpu", 90),
            ("mem", 90),
            ("rss", 100),
            ("state", 80),
        ):
            self.tree.heading(col, text=col.upper())
            self.tree.column(col, width=width, anchor="center")
        self.tree.grid(row=0, column=0, sticky="nsew", padx=8, pady=8)

        ybar = ttk.Scrollbar(procs, orient="vertical", command=self.tree.yview)
        ybar.grid(row=0, column=1, sticky="ns", pady=8)
        self.tree.configure(yscrollcommand=ybar.set)

    def toggle_sort(self) -> None:
        self.sort_mode = "mem" if self.sort_mode == "cpu" else "cpu"
        self.sort_btn.configure(text=f"Sort: {self.sort_mode.upper()}")

    def _tick(self) -> None:
        now = time.time()
        dt = max(0.5, now - self.last_time)
        self.last_time = now

        cpu_now = read_cpu_totals()
        total_delta = cpu_now[0] - self.cpu_prev[0]
        idle_delta = cpu_now[1] - self.cpu_prev[1]
        self.cpu_prev = cpu_now
        cpu_usage = 0.0
        if total_delta > 0:
            cpu_usage = (1.0 - (idle_delta / total_delta)) * 100.0

        mem = read_meminfo()
        mem_total = mem.get("MemTotal", 1) * 1024
        mem_used = (mem.get("MemTotal", 0) - mem.get("MemAvailable", 0)) * 1024
        mem_usage = (mem_used / mem_total) * 100.0 if mem_total else 0.0
        swap_total = mem.get("SwapTotal", 0) * 1024
        swap_used = (mem.get("SwapTotal", 0) - mem.get("SwapFree", 0)) * 1024
        swap_usage = (swap_used / swap_total) * 100.0 if swap_total else 0.0

        disk = shutil.disk_usage("/")
        disk_usage = ((disk.used / disk.total) * 100.0) if disk.total else 0.0

        net_now = read_net_bytes()
        rx_rate = (net_now[0] - self.net_prev[0]) / dt
        tx_rate = (net_now[1] - self.net_prev[1]) / dt
        self.net_prev = net_now

        info = read_chassis_info()
        self.subtitle.configure(
            text=f"{info[0]}  |  {info[1]}  |  Uptime: {read_uptime()}"
        )

        self.cpu_bar["value"] = cpu_usage
        self.mem_bar["value"] = mem_usage
        self.swap_bar["value"] = swap_usage
        self.disk_bar["value"] = disk_usage

        self.cpu_val.configure(text=f"{cpu_usage:5.1f}%")
        self.mem_val.configure(text=f"{mem_usage:5.1f}%  ({human_bytes(mem_used)} / {human_bytes(mem_total)})")
        self.swap_val.configure(text=f"{swap_usage:5.1f}%  ({human_bytes(swap_used)} / {human_bytes(swap_total)})")
        self.disk_val.configure(text=f"{disk_usage:5.1f}%  ({human_bytes(disk.used)} / {human_bytes(disk.total)})")
        self.net_label.configure(text=f"NET  RX {human_bytes(rx_rate)}/s  TX {human_bytes(tx_rate)}/s")

        rows = read_top_processes(sort_mode=self.sort_mode, limit=18)
        for item in self.tree.get_children():
            self.tree.delete(item)
        for row in rows:
            self.tree.insert(
                "",
                "end",
                values=(
                    row["pid"],
                    row["name"],
                    f"{row['cpu']}%",
                    f"{row['mem']}%",
                    row["rss"],
                    row["state"],
                ),
            )

        self.after(1000, self._tick)


def spawn_terminal_tui() -> bool:
    script = "/usr/local/bin/crixa-task-manager.py"
    candidates = [
        ["xterm", "-fa", "DejaVu Sans Mono", "-fs", "10", "-bg", "#0b1220", "-fg", "#dbeafe", "-title", "CRIXA Task Manager", "-e", "python3", script, "--tui"],
        ["alacritty", "--title", "CRIXA Task Manager", "-e", "python3", script, "--tui"],
    ]
    for cmd in candidates:
        if shutil.which(cmd[0]):
            subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return True
    return False


def run_gui() -> int:
    if tk is None or ttk is None:
        return 1
    app = TaskManagerGUI()
    app.mainloop()
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="CRIXA Task Manager")
    parser.add_argument("--tui", action="store_true", help="force terminal mode")
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    if args.tui:
        return run_tui()

    display_ready = bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))
    if display_ready and tk is not None and ttk is not None:
        return run_gui()

    if sys.stdin.isatty():
        return run_tui()

    if display_ready and spawn_terminal_tui():
        return 0

    print("Unable to start CRIXA Task Manager.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
