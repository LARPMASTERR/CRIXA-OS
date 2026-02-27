#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
import tkinter as tk
from tkinter import messagebox, ttk

SYSTEM_BACKEND_DIR = Path("/usr/share/crixa-store/backends")
USER_BACKEND_DIRS = [
    Path.home() / ".local" / "share" / "crixa-store" / "backends",
    Path.home() / ".config" / "crixa-store" / "backends",
]

DEFAULT_BACKEND = "crixa-repo"


@dataclass
class Backend:
    backend_id: str
    name: str
    command: list[str]
    supports_upgrade: bool
    priority: int
    description: str
    manifest_path: Path


def ensure_app_shape(app: dict, source_id: str) -> dict:
    app_id = str(app.get("id", "")).strip()
    name = str(app.get("name", app_id or "Unnamed")).strip() or app_id or "Unnamed"
    return {
        "id": app_id,
        "name": name,
        "version": str(app.get("version", "n/a")),
        "category": str(app.get("category", "General")),
        "summary": str(app.get("summary", "")),
        "description": str(app.get("description", "")),
        "features": app.get("features", []) if isinstance(app.get("features"), list) else [],
        "entrypoint": str(app.get("entrypoint", "")),
        "size": str(app.get("size", "")),
        "installed": bool(app.get("installed", False)),
        "source": str(app.get("source", source_id)),
    }


class CrixaStore(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("CRIXA Store")
        self.geometry("1130x730")
        self.minsize(980, 640)
        self.configure(bg="#0a162b")

        self.backends: list[Backend] = []
        self.backend_map: dict[str, Backend] = {}
        self.filtered_apps: list[dict] = []

        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *_: self.refresh_apps_list())
        self.source_var = tk.StringVar(value=DEFAULT_BACKEND)
        self.source_label_var = tk.StringVar(value="")
        self.status_var = tk.StringVar(value="Store ready")

        self.setup_style()
        self.build_ui()
        self.reload_backends(initial=True)

    def setup_style(self) -> None:
        self.style = ttk.Style(self)
        try:
            self.style.theme_use("clam")
        except tk.TclError:
            pass

        self.colors = {
            "bg": "#0a162b",
            "panel": "#10233f",
            "panel_alt": "#0f2038",
            "accent": "#2f80ed",
            "text": "#dbeafe",
            "muted": "#8ea7cb",
        }
        self.style.configure(".", background=self.colors["bg"], foreground=self.colors["text"], font=("DejaVu Sans", 10))
        self.style.configure("Panel.TFrame", background=self.colors["panel"])
        self.style.configure("PanelAlt.TFrame", background=self.colors["panel_alt"])
        self.style.configure("Title.TLabel", font=("DejaVu Sans", 16, "bold"))
        self.style.configure("Muted.TLabel", foreground=self.colors["muted"])
        self.style.configure("TButton", padding=(12, 8))
        self.style.map("TButton", background=[("active", self.colors["accent"])], foreground=[("active", "#ffffff")])

    def build_ui(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        top = ttk.Frame(self, style="Panel.TFrame")
        top.grid(row=0, column=0, sticky="ew", padx=12, pady=(12, 8))
        top.grid_columnconfigure(2, weight=1)

        ttk.Label(top, text="CRIXA Store", style="Title.TLabel").grid(row=0, column=0, sticky="w", padx=(12, 10), pady=12)

        self.source_combo = ttk.Combobox(top, textvariable=self.source_label_var, state="readonly", width=28)
        self.source_combo.grid(row=0, column=1, sticky="w", padx=(0, 10), pady=12)
        self.source_combo.bind("<<ComboboxSelected>>", lambda _e: self.refresh_apps_list())

        search_entry = ttk.Entry(top, textvariable=self.search_var)
        search_entry.grid(row=0, column=2, sticky="ew", padx=(0, 12), pady=12)

        body = ttk.Frame(self, style="PanelAlt.TFrame")
        body.grid(row=1, column=0, sticky="nsew", padx=12, pady=8)
        body.grid_columnconfigure(1, weight=1)
        body.grid_rowconfigure(0, weight=1)

        left = ttk.Frame(body, style="Panel.TFrame")
        left.grid(row=0, column=0, sticky="nsw", padx=(12, 8), pady=12)
        left.grid_rowconfigure(1, weight=1)

        ttk.Label(left, text="Applications").grid(row=0, column=0, sticky="w", padx=8, pady=(8, 4))
        self.apps_listbox = tk.Listbox(
            left,
            width=42,
            height=30,
            bg="#0d1d33",
            fg="#dbeafe",
            selectbackground="#2f80ed",
            selectforeground="#ffffff",
            relief="flat",
            highlightthickness=0,
            activestyle="none",
            font=("DejaVu Sans", 10),
        )
        self.apps_listbox.grid(row=1, column=0, sticky="nsew", padx=8, pady=(0, 8))
        self.apps_listbox.bind("<<ListboxSelect>>", lambda _e: self.on_select())

        self.count_label = ttk.Label(left, text="0 apps", style="Muted.TLabel")
        self.count_label.grid(row=2, column=0, sticky="w", padx=8, pady=(0, 8))

        right = ttk.Frame(body, style="Panel.TFrame")
        right.grid(row=0, column=1, sticky="nsew", padx=(8, 12), pady=12)
        right.grid_columnconfigure(0, weight=1)
        right.grid_rowconfigure(1, weight=1)

        self.title_var = tk.StringVar(value="Select an app")
        self.meta_var = tk.StringVar(value="")
        ttk.Label(right, textvariable=self.title_var, style="Title.TLabel").grid(row=0, column=0, sticky="w", padx=12, pady=(12, 2))
        ttk.Label(right, textvariable=self.meta_var, style="Muted.TLabel").grid(row=0, column=0, sticky="w", padx=12, pady=(40, 10))

        self.details_text = tk.Text(
            right,
            wrap="word",
            bg="#0b1a30",
            fg="#dbeafe",
            relief="flat",
            highlightthickness=0,
            padx=12,
            pady=12,
            font=("DejaVu Sans", 10),
        )
        self.details_text.grid(row=1, column=0, sticky="nsew", padx=12, pady=(0, 8))
        self.details_text.configure(state="disabled")

        actions = ttk.Frame(right, style="PanelAlt.TFrame")
        actions.grid(row=2, column=0, sticky="ew", padx=12, pady=(0, 12))
        self.install_btn = ttk.Button(actions, text="Install", command=self.install_selected)
        self.install_btn.pack(side="left", padx=(0, 8))
        self.remove_btn = ttk.Button(actions, text="Remove", command=self.remove_selected)
        self.remove_btn.pack(side="left", padx=8)
        self.launch_btn = ttk.Button(actions, text="Launch", command=self.launch_selected)
        self.launch_btn.pack(side="left", padx=8)
        self.upgrade_btn = ttk.Button(actions, text="Upgrade Source", command=self.upgrade_selected_backend)
        self.upgrade_btn.pack(side="left", padx=8)
        ttk.Button(actions, text="Backends Folder", command=self.open_user_backend_folder).pack(side="left", padx=8)
        ttk.Button(actions, text="Reload Backends", command=self.reload_backends).pack(side="left", padx=8)
        ttk.Button(actions, text="Close", command=self.destroy).pack(side="right")

        status = ttk.Label(self, textvariable=self.status_var, style="Muted.TLabel")
        status.grid(row=2, column=0, sticky="ew", padx=20, pady=(4, 10))

    def set_status(self, text: str) -> None:
        self.status_var.set(text)

    def command_for_manifest(self, manifest: dict, manifest_path: Path) -> list[str]:
        command_raw = str(manifest.get("command", "")).strip()
        if not command_raw:
            return []
        command_path = Path(command_raw)
        if not command_path.is_absolute():
            command_path = (manifest_path.parent / command_path).resolve()
        if command_path.suffix == ".py":
            python = shutil.which("python3")
            if not python:
                return []
            return [python, str(command_path)]
        return [str(command_path)]

    def load_backends(self) -> list[Backend]:
        backends: list[Backend] = []
        discovered_ids: set[str] = set()
        search_dirs = [SYSTEM_BACKEND_DIR, *USER_BACKEND_DIRS]
        for folder in search_dirs:
            if not folder.exists():
                continue
            for manifest_path in sorted(folder.glob("*.json")):
                try:
                    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                except Exception:
                    continue
                if not isinstance(manifest, dict):
                    continue
                backend_id = str(manifest.get("id", "")).strip()
                name = str(manifest.get("name", backend_id)).strip()
                if not backend_id or not name or backend_id in discovered_ids:
                    continue
                command = self.command_for_manifest(manifest, manifest_path)
                if not command:
                    continue
                supports_upgrade = bool(manifest.get("supports_upgrade", True))
                priority = int(manifest.get("priority", 100))
                description = str(manifest.get("description", "")).strip()
                backends.append(
                    Backend(
                        backend_id=backend_id,
                        name=name,
                        command=command,
                        supports_upgrade=supports_upgrade,
                        priority=priority,
                        description=description,
                        manifest_path=manifest_path,
                    )
                )
                discovered_ids.add(backend_id)
        return sorted(backends, key=lambda row: (row.priority, row.name.lower()))

    def selected_backend(self) -> Backend | None:
        backend_id = self.source_var.get().strip()
        return self.backend_map.get(backend_id)

    def call_backend(self, backend: Backend, payload: dict, timeout_sec: int = 300) -> tuple[bool, dict]:
        try:
            result = subprocess.run(
                backend.command,
                input=json.dumps(payload),
                capture_output=True,
                text=True,
                timeout=timeout_sec,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return False, {"ok": False, "error": f"{backend.name} backend timed out"}
        except Exception as exc:
            return False, {"ok": False, "error": str(exc)}

        output = result.stdout.strip()
        try:
            parsed = json.loads(output) if output else {}
        except json.JSONDecodeError:
            parsed = {"ok": False, "error": output or result.stderr.strip() or "invalid backend response"}

        if result.returncode != 0 and not parsed.get("ok", False):
            err = parsed.get("error") or parsed.get("message") or result.stderr.strip() or "backend command failed"
            return False, {"ok": False, "error": err}
        return bool(parsed.get("ok", False)), parsed

    def reload_backends(self, initial: bool = False) -> None:
        previous = self.source_var.get().strip()
        self.backends = self.load_backends()
        self.backend_map = {row.backend_id: row for row in self.backends}

        if not self.backends:
            self.source_combo.configure(values=[])
            self.source_var.set("")
            self.source_label_var.set("")
            self.apps_listbox.delete(0, tk.END)
            self.set_status("No store backends found")
            return

        labels = [f"{row.name} [{row.backend_id}]" for row in self.backends]
        self.source_combo.configure(values=labels)

        selected_id = previous if previous in self.backend_map else DEFAULT_BACKEND
        if selected_id not in self.backend_map:
            selected_id = self.backends[0].backend_id
        self.source_var.set(selected_id)
        self.source_label_var.set(f"{self.backend_map[selected_id].name} [{selected_id}]")
        self.refresh_apps_list()
        if not initial:
            self.set_status(f"Loaded {len(self.backends)} backend(s)")

    def normalize_source_combo_selection(self) -> None:
        raw = self.source_combo.get().strip()
        if raw.endswith("]") and "[" in raw:
            selected_id = raw.rsplit("[", 1)[1].rstrip("]").strip()
            if selected_id in self.backend_map:
                self.source_var.set(selected_id)
                self.source_label_var.set(raw)

    def selected_app(self) -> dict | None:
        if not self.apps_listbox.curselection():
            return None
        idx = self.apps_listbox.curselection()[0]
        if idx < 0 or idx >= len(self.filtered_apps):
            return None
        return self.filtered_apps[idx]

    def refresh_apps_list(self, selected_id: str | None = None) -> None:
        self.normalize_source_combo_selection()
        backend = self.selected_backend()
        if backend is None:
            self.filtered_apps = []
            self.apps_listbox.delete(0, tk.END)
            self.on_select()
            self.set_status("No backend selected")
            return

        query = self.search_var.get().strip()
        ok, payload = self.call_backend(
            backend,
            {
                "action": "list",
                "query": query,
                "limit": 260,
            },
        )
        if not ok:
            self.filtered_apps = []
            self.apps_listbox.delete(0, tk.END)
            self.count_label.configure(text="backend error")
            self.on_select()
            self.set_status(payload.get("error", "Backend query failed"))
            return

        apps = payload.get("apps", [])
        if not isinstance(apps, list):
            apps = []
        normalized = [ensure_app_shape(item, backend.backend_id) for item in apps if isinstance(item, dict)]
        self.filtered_apps = normalized

        self.apps_listbox.delete(0, tk.END)
        selected_idx = None
        installed_count = 0
        for idx, app in enumerate(self.filtered_apps):
            if app.get("installed"):
                installed_count += 1
            prefix = "[Installed] " if app.get("installed") else ""
            self.apps_listbox.insert(tk.END, f"{prefix}{app.get('name', app.get('id', '?'))}")
            if selected_id and app.get("id") == selected_id:
                selected_idx = idx

        desc = backend.description or f"Source: {backend.name}"
        self.count_label.configure(text=f"{len(self.filtered_apps)} shown  |  {installed_count} installed  |  {desc}")

        if selected_idx is not None:
            self.apps_listbox.selection_set(selected_idx)
        elif self.filtered_apps:
            self.apps_listbox.selection_set(0)
        self.on_select()

        note = payload.get("message", "")
        self.set_status(note or f"Loaded {len(self.filtered_apps)} app(s) from {backend.name}")

    def on_select(self) -> None:
        backend = self.selected_backend()
        app = self.selected_app()
        if not app or backend is None:
            self.title_var.set("Select an app")
            self.meta_var.set("")
            self.update_details("")
            self.install_btn.configure(state="disabled")
            self.remove_btn.configure(state="disabled")
            self.launch_btn.configure(state="disabled")
            self.upgrade_btn.configure(state="disabled")
            return

        app_id = app.get("id", "")
        installed = bool(app.get("installed", False))
        self.title_var.set(app.get("name", app_id))
        self.meta_var.set(
            f"Version {app.get('version', 'n/a')}  |  {app.get('category', 'General')}  |  Source {backend.name}"
        )

        features = app.get("features", [])
        feature_lines = "\n".join(f"  - {item}" for item in features) if features else "  - No feature list provided"
        details = (
            f"{app.get('summary', '')}\n\n"
            f"{app.get('description', '')}\n\n"
            f"Backend: {backend.backend_id}\n"
            f"App ID: {app_id}\n\n"
            f"Highlights:\n{feature_lines}"
        )
        self.update_details(details)

        self.install_btn.configure(text="Update" if installed else "Install", state="normal")
        self.remove_btn.configure(state="normal" if installed else "disabled")
        self.launch_btn.configure(state="normal" if installed else "disabled")
        self.upgrade_btn.configure(state="normal" if backend.supports_upgrade else "disabled")

    def update_details(self, text: str) -> None:
        self.details_text.configure(state="normal")
        self.details_text.delete("1.0", tk.END)
        self.details_text.insert("1.0", text)
        self.details_text.configure(state="disabled")

    def call_action_on_selected(self, action: str, force: bool = False) -> tuple[bool, str]:
        backend = self.selected_backend()
        app = self.selected_app()
        if backend is None or app is None:
            return False, "No app selected"
        timeout_sec = 300
        if action in ("install", "remove"):
            timeout_sec = 1800
        elif action == "launch":
            timeout_sec = 30
        ok, payload = self.call_backend(
            backend,
            {
                "action": action,
                "app_id": app.get("id", ""),
                "force": force,
            },
            timeout_sec=timeout_sec,
        )
        message = payload.get("message", "") if isinstance(payload, dict) else ""
        if ok:
            return True, message or f"{action} completed"
        err = payload.get("error", "backend action failed") if isinstance(payload, dict) else "backend action failed"
        return False, err

    def install_selected(self) -> None:
        app = self.selected_app()
        if not app:
            return
        force = False
        if app.get("installed"):
            force = messagebox.askyesno("Update App", f"{app.get('name')} is already installed.\nReinstall/update now?")
            if not force:
                return
        ok, msg = self.call_action_on_selected("install", force=force)
        if not ok:
            messagebox.showerror("Install Failed", msg)
            return
        self.refresh_apps_list(selected_id=app.get("id", ""))
        self.set_status(msg)

    def remove_selected(self) -> None:
        app = self.selected_app()
        if not app:
            return
        if not app.get("installed"):
            return
        if not messagebox.askyesno("Remove App", f"Remove {app.get('name')}?"):
            return
        ok, msg = self.call_action_on_selected("remove")
        if not ok:
            messagebox.showerror("Remove Failed", msg)
            return
        self.refresh_apps_list(selected_id=app.get("id", ""))
        self.set_status(msg)

    def launch_selected(self) -> None:
        ok, msg = self.call_action_on_selected("launch")
        if not ok:
            messagebox.showerror("Launch Failed", msg)
            return
        self.set_status(msg)

    def upgrade_selected_backend(self) -> None:
        backend = self.selected_backend()
        if backend is None:
            return
        if not backend.supports_upgrade:
            messagebox.showinfo("CRIXA Store", "Selected backend does not support bulk upgrade.")
            return
        ok, payload = self.call_backend(backend, {"action": "upgrade"}, timeout_sec=3600)
        if not ok:
            messagebox.showerror("Upgrade Failed", payload.get("error", "upgrade failed"))
            return
        self.refresh_apps_list()
        self.set_status(payload.get("message", "Upgrade complete"))

    def open_user_backend_folder(self) -> None:
        path = USER_BACKEND_DIRS[-1]
        path.mkdir(parents=True, exist_ok=True)
        try:
            subprocess.Popen(["thunar", str(path)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            pass


def main() -> int:
    app = CrixaStore()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
