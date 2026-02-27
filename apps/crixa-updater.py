#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import subprocess
import tkinter as tk
from tkinter import messagebox, ttk


def run_cmd(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, capture_output=True, text=True, check=False)


def run_json(args: list[str]) -> dict:
    result = run_cmd(args)
    if result.returncode != 0:
        msg = (result.stderr or result.stdout).strip() or f"command failed: {' '.join(args)}"
        raise RuntimeError(msg)
    try:
        return json.loads(result.stdout or "{}")
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"invalid json from {' '.join(args)}") from exc


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


class CrixaUpdater(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("CRIXA Updater")
        self.geometry("980x700")
        self.minsize(860, 620)
        self.configure(bg="#0a162b")

        self.status_var = tk.StringVar(value="Ready")
        self.rollout_summary = tk.StringVar(value="Track: stable  |  Current: 0.0.0")
        self.rollout_details = tk.StringVar(value="No rollout status loaded yet.")
        self.snapshots: list[dict] = []

        self.build_ui()
        self.refresh_all()

    def build_ui(self) -> None:
        root = ttk.Frame(self)
        root.pack(fill="both", expand=True, padx=12, pady=12)
        root.columnconfigure(0, weight=1)
        root.columnconfigure(1, weight=1)
        root.rowconfigure(1, weight=1)

        header = ttk.Frame(root)
        header.grid(row=0, column=0, columnspan=2, sticky="ew")
        ttk.Label(header, text="CRIXA Atomic Updater", font=("DejaVu Sans", 15, "bold")).pack(side="left")
        ttk.Button(header, text="Refresh", command=self.refresh_all).pack(side="right", padx=(8, 0))
        ttk.Button(header, text="Upgrade All", command=self.upgrade_all).pack(side="right", padx=(8, 0))

        updates_frame = ttk.LabelFrame(root, text="Pending App Updates")
        updates_frame.grid(row=1, column=0, sticky="nsew", padx=(0, 8), pady=(10, 8))
        updates_frame.rowconfigure(0, weight=1)
        updates_frame.columnconfigure(0, weight=1)
        self.updates_list = tk.Listbox(
            updates_frame,
            bg="#0e2039",
            fg="#dbeafe",
            selectbackground="#2f80ed",
            relief="flat",
            highlightthickness=0,
            activestyle="none",
            font=("DejaVu Sans", 10),
        )
        self.updates_list.grid(row=0, column=0, sticky="nsew", padx=8, pady=8)

        right_col = ttk.Frame(root)
        right_col.grid(row=1, column=1, sticky="nsew", padx=(8, 0), pady=(10, 8))
        right_col.rowconfigure(1, weight=1)
        right_col.columnconfigure(0, weight=1)

        rollout_frame = ttk.LabelFrame(right_col, text="System Rollout Channel")
        rollout_frame.grid(row=0, column=0, sticky="ew")
        rollout_frame.columnconfigure(0, weight=1)

        ttk.Label(rollout_frame, textvariable=self.rollout_summary).grid(row=0, column=0, sticky="w", padx=8, pady=(8, 2))
        ttk.Label(rollout_frame, textvariable=self.rollout_details, justify="left").grid(
            row=1, column=0, sticky="w", padx=8, pady=(0, 8)
        )

        rollout_btns = ttk.Frame(rollout_frame)
        rollout_btns.grid(row=2, column=0, sticky="ew", padx=8, pady=(0, 8))
        ttk.Button(rollout_btns, text="Stable", command=lambda: self.switch_track("stable")).pack(side="left")
        ttk.Button(rollout_btns, text="Beta", command=lambda: self.switch_track("beta")).pack(side="left", padx=(8, 0))
        ttk.Button(rollout_btns, text="Canary", command=lambda: self.switch_track("canary")).pack(side="left", padx=(8, 0))

        snapshots_frame = ttk.LabelFrame(right_col, text="Rollback Snapshots")
        snapshots_frame.grid(row=1, column=0, sticky="nsew", pady=(8, 0))
        snapshots_frame.rowconfigure(0, weight=1)
        snapshots_frame.columnconfigure(0, weight=1)
        self.snapshots_list = tk.Listbox(
            snapshots_frame,
            bg="#0e2039",
            fg="#dbeafe",
            selectbackground="#2f80ed",
            relief="flat",
            highlightthickness=0,
            activestyle="none",
            font=("DejaVu Sans", 10),
        )
        self.snapshots_list.grid(row=0, column=0, sticky="nsew", padx=8, pady=(8, 4))
        btn_row = ttk.Frame(snapshots_frame)
        btn_row.grid(row=1, column=0, sticky="ew", padx=8, pady=(0, 8))
        ttk.Button(btn_row, text="Rollback Selected", command=self.rollback_selected).pack(side="left")
        ttk.Button(btn_row, text="Rollback Latest", command=self.rollback_latest).pack(side="left", padx=(8, 0))

        log_frame = ttk.LabelFrame(root, text="Command Log")
        log_frame.grid(row=2, column=0, columnspan=2, sticky="nsew")
        log_frame.rowconfigure(0, weight=1)
        log_frame.columnconfigure(0, weight=1)
        self.log = tk.Text(
            log_frame,
            height=10,
            bg="#081326",
            fg="#dbeafe",
            relief="flat",
            highlightthickness=0,
            font=("DejaVu Sans Mono", 10),
            padx=10,
            pady=10,
        )
        self.log.grid(row=0, column=0, sticky="nsew", padx=8, pady=8)
        self.log.configure(state="disabled")

        ttk.Label(root, textvariable=self.status_var).grid(row=3, column=0, columnspan=2, sticky="ew", pady=(8, 0))

    def append_log(self, text: str) -> None:
        self.log.configure(state="normal")
        self.log.insert("end", text.rstrip() + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def refresh_all(self) -> None:
        errors: list[str] = []
        for loader in (self.refresh_updates, self.refresh_rollout, self.refresh_snapshots):
            try:
                loader()
            except Exception as exc:
                errors.append(str(exc))
        if errors:
            self.status_var.set("Refresh completed with warnings")
            messagebox.showerror("CRIXA Updater", "\n".join(errors))
            return
        self.status_var.set("Updater state refreshed")

    def refresh_updates(self) -> None:
        installed = run_json(["crixapkg", "installed", "--json"]).get("apps", [])
        available = run_json(["crixapkg", "list", "--json"]).get("packages", [])
        avail_map = {str(item.get("id", "")): item for item in available if isinstance(item, dict)}

        pending = []
        for app in installed:
            if not isinstance(app, dict):
                continue
            app_id = str(app.get("id", ""))
            installed_ver = str(app.get("version", "0"))
            avail = avail_map.get(app_id)
            if not avail:
                continue
            repo_ver = str(avail.get("version", "0"))
            if version_key(repo_ver) > version_key(installed_ver):
                pending.append(f"{app_id}  {installed_ver} -> {repo_ver}")

        self.updates_list.delete(0, tk.END)
        for row in pending:
            self.updates_list.insert(tk.END, row)
        if not pending:
            self.updates_list.insert(tk.END, "No updates pending")

    def refresh_rollout(self) -> None:
        payload = run_json(["crixa-releasectl", "status", "--json"])
        current = payload.get("current", {})
        status = payload.get("status", {})
        if not isinstance(current, dict) or not isinstance(status, dict):
            raise RuntimeError("invalid rollout status payload")

        track = str(status.get("track", current.get("track", "stable")))
        current_version = str(current.get("version", "0.0.0"))
        target_version = str(status.get("release_version", current_version))
        eligible = bool(status.get("eligible", False))
        reason = str(status.get("reason", "unknown"))
        rollout_percent = float(status.get("rollout_percent", 0.0))
        bucket_percent = float(status.get("bucket_percent", 0.0))

        self.rollout_summary.set(f"Track: {track}  |  Current: {current_version}  |  Target: {target_version}")
        self.rollout_details.set(
            f"Eligible: {'yes' if eligible else 'no'}\n"
            f"Reason: {reason}\n"
            f"Rollout: {rollout_percent:.1f}%   Bucket: {bucket_percent:.1f}%"
        )

    def switch_track(self, track: str) -> None:
        if not messagebox.askyesno("Switch Track", f"Switch update track to '{track}'?"):
            return

        cmd = ["crixa-releasectl", "switch-track", track, "--json"]
        shown_cmd = " ".join(cmd)
        if os.geteuid() != 0:
            cmd.insert(0, "sudo")
            shown_cmd = "sudo " + shown_cmd

        self.append_log(f"$ {shown_cmd}")
        result = run_cmd(cmd)
        if result.stdout:
            self.append_log(result.stdout.strip())
        if result.stderr:
            self.append_log(result.stderr.strip())
        if result.returncode != 0:
            self.status_var.set("Track switch failed")
            messagebox.showerror("CRIXA Updater", "Failed to switch track. Check command log output.")
            return

        self.status_var.set(f"Track switched to {track}")
        self.refresh_all()

    def refresh_snapshots(self) -> None:
        payload = run_json(["crixapkg", "history", "--json"])
        rows = payload.get("snapshots", [])
        self.snapshots = [row for row in rows if isinstance(row, dict)]

        self.snapshots_list.delete(0, tk.END)
        for row in self.snapshots:
            snap_id = str(row.get("id", ""))
            reason = str(row.get("reason", ""))
            created = str(row.get("created_at", ""))
            self.snapshots_list.insert(tk.END, f"{snap_id}  |  {reason}  |  {created}")
        if not self.snapshots:
            self.snapshots_list.insert(tk.END, "No snapshots available")

    def upgrade_all(self) -> None:
        self.append_log("$ crixapkg upgrade --json")
        result = run_cmd(["crixapkg", "upgrade", "--json"])
        if result.stdout:
            self.append_log(result.stdout.strip())
        if result.stderr:
            self.append_log(result.stderr.strip())
        if result.returncode != 0:
            self.status_var.set("Upgrade failed")
            messagebox.showerror("CRIXA Updater", "Upgrade failed. Check log output.")
            return
        self.status_var.set("Upgrade completed")
        self.refresh_all()

    def rollback_selected(self) -> None:
        if not self.snapshots:
            return
        if not self.snapshots_list.curselection():
            messagebox.showinfo("CRIXA Updater", "Select a snapshot first.")
            return
        idx = self.snapshots_list.curselection()[0]
        if idx < 0 or idx >= len(self.snapshots):
            return
        snap_id = str(self.snapshots[idx].get("id", ""))
        if not snap_id:
            return
        self.rollback_to(snap_id)

    def rollback_latest(self) -> None:
        self.rollback_to("latest")

    def rollback_to(self, snap_id: str) -> None:
        if not messagebox.askyesno("Confirm Rollback", f"Rollback using snapshot: {snap_id}\n\nContinue?"):
            return
        self.append_log(f"$ crixapkg rollback {snap_id} --json")
        result = run_cmd(["crixapkg", "rollback", snap_id, "--json"])
        if result.stdout:
            self.append_log(result.stdout.strip())
        if result.stderr:
            self.append_log(result.stderr.strip())
        if result.returncode != 0:
            self.status_var.set("Rollback failed")
            messagebox.showerror("CRIXA Updater", "Rollback failed. Check log output.")
            return
        self.status_var.set("Rollback completed")
        self.refresh_all()


def main() -> int:
    app = CrixaUpdater()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
