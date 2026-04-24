#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import threading
import tkinter as tk
from pathlib import Path
from queue import Empty, Queue
from tkinter import messagebox, ttk

INSTALLER_BIN = "/usr/local/sbin/crixa-install"


def run_cmd(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, capture_output=True, text=True, check=False)


class CrixaInstaller(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Dockyard")
        self.geometry("980x700")
        self.minsize(860, 620)
        self.configure(bg="#09152a")

        self.style = ttk.Style(self)
        try:
            self.style.theme_use("clam")
        except tk.TclError:
            pass
        self.style.configure(".", font=("DejaVu Sans", 10))

        self.queue: Queue[tuple[str, str]] = Queue()
        self.worker: threading.Thread | None = None
        self.proc: subprocess.Popen[str] | None = None

        self.disk_var = tk.StringVar()
        self.hostname_var = tk.StringVar(value="crixa-os")
        self.user_var = tk.StringVar(value="crixa")
        self.timezone_var = tk.StringVar(value="UTC")
        self.password_var = tk.StringVar(value="")
        self.status_var = tk.StringVar(value="Select a target disk and click Install.")
        self.disk_values: list[str] = []

        self._build_ui()
        self.refresh_disks()
        self.after(120, self._drain_queue)

    def _build_ui(self) -> None:
        root = ttk.Frame(self)
        root.pack(fill="both", expand=True, padx=14, pady=14)

        header = ttk.Label(
            root,
            text="Dockyard",
            font=("DejaVu Sans", 16, "bold"),
        )
        header.pack(anchor="w", pady=(0, 6))
        ttk.Label(
            root,
            text="This installs CRIXA from live mode to a disk. The selected disk will be fully erased.",
        ).pack(anchor="w", pady=(0, 12))

        form = ttk.LabelFrame(root, text="Install Target")
        form.pack(fill="x", pady=(0, 10))
        form.columnconfigure(1, weight=1)

        ttk.Label(form, text="Disk:").grid(row=0, column=0, sticky="w", padx=12, pady=(10, 6))
        self.disk_combo = ttk.Combobox(form, textvariable=self.disk_var, state="readonly")
        self.disk_combo.grid(row=0, column=1, sticky="ew", padx=(0, 12), pady=(10, 6))
        ttk.Button(form, text="Refresh", command=self.refresh_disks).grid(row=0, column=2, padx=(0, 12), pady=(10, 6))

        ttk.Label(form, text="Hostname:").grid(row=1, column=0, sticky="w", padx=12, pady=6)
        ttk.Entry(form, textvariable=self.hostname_var).grid(row=1, column=1, sticky="ew", padx=(0, 12), pady=6)

        ttk.Label(form, text="User:").grid(row=2, column=0, sticky="w", padx=12, pady=6)
        ttk.Entry(form, textvariable=self.user_var).grid(row=2, column=1, sticky="ew", padx=(0, 12), pady=6)

        ttk.Label(form, text="Timezone:").grid(row=3, column=0, sticky="w", padx=12, pady=6)
        ttk.Entry(form, textvariable=self.timezone_var).grid(row=3, column=1, sticky="ew", padx=(0, 12), pady=6)

        ttk.Label(form, text="User Password (optional):").grid(row=4, column=0, sticky="w", padx=12, pady=(6, 10))
        ttk.Entry(form, textvariable=self.password_var, show="*").grid(row=4, column=1, sticky="ew", padx=(0, 12), pady=(6, 10))

        actions = ttk.Frame(root)
        actions.pack(fill="x", pady=(0, 8))
        self.install_btn = ttk.Button(actions, text="Install CRIXA", command=self.start_install)
        self.install_btn.pack(side="left", padx=(0, 8))
        ttk.Button(actions, text="Open Installer Log", command=self.open_log).pack(side="left", padx=8)
        ttk.Button(actions, text="Close", command=self.destroy).pack(side="right")

        ttk.Label(root, textvariable=self.status_var).pack(anchor="w", pady=(0, 6))

        log_wrap = ttk.LabelFrame(root, text="Live Log")
        log_wrap.pack(fill="both", expand=True)
        self.log_text = tk.Text(
            log_wrap,
            wrap="word",
            bg="#071223",
            fg="#dbeafe",
            insertbackground="#dbeafe",
            relief="flat",
            padx=10,
            pady=10,
        )
        self.log_text.pack(fill="both", expand=True, padx=8, pady=8)
        self.log_text.insert("end", "Dockyard ready.\n")
        self.log_text.configure(state="disabled")

    def append_log(self, line: str) -> None:
        self.log_text.configure(state="normal")
        self.log_text.insert("end", line)
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def refresh_disks(self) -> None:
        result = run_cmd(["lsblk", "-J", "-o", "PATH,SIZE,MODEL,TYPE,RM"])
        if result.returncode != 0:
            self.status_var.set("Failed to enumerate disks.")
            return
        try:
            payload = json.loads(result.stdout or "{}")
        except json.JSONDecodeError:
            self.status_var.set("lsblk returned invalid JSON.")
            return

        devices = []
        for item in payload.get("blockdevices", []):
            if not isinstance(item, dict):
                continue
            if item.get("type") != "disk":
                continue
            path = str(item.get("path") or "").strip()
            if not path:
                continue
            if path.startswith("/dev/loop") or path.startswith("/dev/ram") or path.startswith("/dev/zram"):
                continue
            if path.startswith("/dev/sr"):
                continue
            size = str(item.get("size") or "?")
            model = str(item.get("model") or "").strip() or "Unknown"
            rm = str(item.get("rm") or "0")
            removable = "removable" if rm == "1" else "fixed"
            label = f"{path}  |  {size}  |  {model}  |  {removable}"
            devices.append(label)

        self.disk_values = devices
        self.disk_combo.configure(values=devices)
        if devices and not self.disk_var.get():
            self.disk_var.set(devices[0])
        self.status_var.set(f"Detected {len(devices)} installable disk(s).")

    def selected_disk(self) -> str:
        value = self.disk_var.get().strip()
        if not value:
            return ""
        return value.split("  |  ", 1)[0].strip()

    def start_install(self) -> None:
        if self.worker and self.worker.is_alive():
            messagebox.showinfo("Installer Busy", "An install is already running.")
            return
        target = self.selected_disk()
        if not target:
            messagebox.showerror("No Target", "Choose a disk first.")
            return

        hostname = self.hostname_var.get().strip() or "crixa-os"
        user = self.user_var.get().strip() or "crixa"
        timezone = self.timezone_var.get().strip() or "UTC"
        password = self.password_var.get()

        if not messagebox.askyesno(
            "Confirm Install",
            f"This will erase all data on:\n{target}\n\nContinue?",
        ):
            return

        cmd = [
            "sudo",
            "-n",
            INSTALLER_BIN,
            "--target",
            target,
            "--hostname",
            hostname,
            "--user",
            user,
            "--timezone",
            timezone,
            "--yes",
        ]
        if password:
            cmd.extend(["--user-password", password])

        self.install_btn.configure(state="disabled")
        self.status_var.set(f"Dockyard is installing to {target} ...")
        self.append_log(f"\n$ {' '.join(cmd)}\n")

        self.worker = threading.Thread(target=self._run_installer, args=(cmd,), daemon=True)
        self.worker.start()

    def _run_installer(self, cmd: list[str]) -> None:
        try:
            self.proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
        except Exception as exc:
            self.queue.put(("status", f"Failed to start installer: {exc}"))
            self.queue.put(("done", "1"))
            return

        assert self.proc.stdout is not None
        for line in self.proc.stdout:
            self.queue.put(("log", line))
        code = self.proc.wait()
        self.queue.put(("status", "Install complete." if code == 0 else f"Installer failed (exit {code})."))
        self.queue.put(("done", str(code)))

    def _drain_queue(self) -> None:
        try:
            while True:
                kind, payload = self.queue.get_nowait()
                if kind == "log":
                    self.append_log(payload)
                elif kind == "status":
                    self.status_var.set(payload)
                elif kind == "done":
                    self.install_btn.configure(state="normal")
        except Empty:
            pass
        self.after(120, self._drain_queue)

    def open_log(self) -> None:
        log_path = Path("/var/log/crixa-installer.log")
        if log_path.exists():
            subprocess.Popen(["crixa-files", str(log_path.parent)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            messagebox.showinfo("Log Not Found", "Installer log has not been created yet.")


def main() -> int:
    if not Path(INSTALLER_BIN).exists():
        messagebox.showerror("Missing Installer", f"Installer backend not found:\n{INSTALLER_BIN}")
        return 1
    app = CrixaInstaller()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
