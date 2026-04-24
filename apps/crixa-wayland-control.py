#!/usr/bin/env python3
from __future__ import annotations

import subprocess
import tkinter as tk
from tkinter import messagebox, ttk


def run_cmd(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, capture_output=True, text=True, check=False)


def parse_mode(text: str) -> str:
    for line in text.splitlines():
        if line.startswith("mode="):
            return line.split("=", 1)[1].strip()
    return "x11"


class CrixaWaylandControl(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Session Lab")
        self.geometry("760x420")
        self.minsize(680, 380)
        self.configure(bg="#081326")

        self.mode_var = tk.StringVar(value="x11")
        self.status_var = tk.StringVar(value="Ready")
        self.build_ui()
        self.refresh_status()

    def build_ui(self) -> None:
        root = ttk.Frame(self)
        root.pack(fill="both", expand=True, padx=14, pady=14)

        ttk.Label(root, text="Session Lab", font=("DejaVu Sans", 15, "bold")).pack(anchor="w")
        ttk.Label(
            root,
            text="Choose the default SDDM session for the next login. X11 stays the safer default; Wayland is available when you want it.",
        ).pack(anchor="w", pady=(4, 10))

        card = ttk.LabelFrame(root, text="Session Mode")
        card.pack(fill="x", pady=(0, 10))
        ttk.Label(card, text="Current mode:").grid(row=0, column=0, sticky="w", padx=12, pady=(12, 6))
        ttk.Label(card, textvariable=self.mode_var, font=("DejaVu Sans", 11, "bold")).grid(row=0, column=1, sticky="w", padx=8, pady=(12, 6))

        row = ttk.Frame(card)
        row.grid(row=1, column=0, columnspan=2, sticky="ew", padx=12, pady=(8, 12))
        ttk.Button(row, text="Use Plasma X11", command=lambda: self.set_mode("x11")).pack(side="left", padx=(0, 8))
        ttk.Button(row, text="Use Plasma Wayland", command=lambda: self.set_mode("wayland")).pack(side="left", padx=8)
        ttk.Button(row, text="Refresh", command=self.refresh_status).pack(side="left", padx=8)

        notes = ttk.LabelFrame(root, text="Notes")
        notes.pack(fill="both", expand=True)
        text = (
            "1. Plasma X11 remains the default path and is recommended for VM stability.\n"
            "2. Plasma Wayland updates the SDDM autologin session for the next login.\n"
            "3. After switching mode, log out or reboot to apply.\n"
            "4. CRIXA now boots directly into Plasma, so there is no separate custom Wayland shell to maintain."
        )
        label = tk.Label(
            notes,
            text=text,
            justify="left",
            anchor="nw",
            bg="#081326",
            fg="#dbeafe",
            font=("DejaVu Sans", 10),
        )
        label.pack(fill="both", expand=True, padx=12, pady=12)

        ttk.Label(root, textvariable=self.status_var).pack(anchor="w", pady=(8, 0))

    def refresh_status(self) -> None:
        result = run_cmd(["crixa-session-mode", "status"])
        if result.returncode != 0:
            self.status_var.set("Failed to read session mode")
            return
        mode = parse_mode(result.stdout)
        self.mode_var.set(self.mode_label(mode))
        self.status_var.set(f"Session mode: {self.mode_label(mode)}")

    def set_mode(self, mode: str) -> None:
        result = run_cmd(["crixa-session-mode", "set", mode])
        if result.returncode != 0:
            details = (result.stderr or result.stdout).strip()
            messagebox.showerror("Session Mode", details or "Failed to set session mode.")
            return
        self.refresh_status()
        self.status_var.set(f"Next login will use {self.mode_label(mode)}.")

    @staticmethod
    def mode_label(mode: str) -> str:
        if mode == "wayland":
            return "Plasma Wayland"
        return "Plasma X11"


def main() -> int:
    app = CrixaWaylandControl()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
