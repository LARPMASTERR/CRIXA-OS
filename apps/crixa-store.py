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
SYSTEM_CATALOG_PATH = Path("/usr/share/crixa-store/catalog.json")
USER_BACKEND_DIRS = [
    Path.home() / ".local" / "share" / "crixa-store" / "backends",
    Path.home() / ".config" / "crixa-store" / "backends",
]
DEV_ROOT = Path(__file__).resolve().parents[1] if Path(__file__).resolve().parent.name == "apps" else None
DEV_BACKEND_DIR = DEV_ROOT / "store-backends" / "manifests" if DEV_ROOT else None
DEV_CATALOG_PATH = DEV_ROOT / "store-packages" / "catalog.json" if DEV_ROOT else None

DEFAULT_BACKEND = "crixa-repo"
ALL_CATEGORIES = "All"
INSTALLED_CATEGORY = "Installed"


@dataclass(slots=True)
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
    tags = app.get("tags", [])
    if not isinstance(tags, list):
        tags = []
    features = app.get("features", [])
    if not isinstance(features, list):
        features = []
    return {
        "id": app_id,
        "name": name,
        "version": str(app.get("version", "n/a")),
        "category": str(app.get("category", "General")),
        "summary": str(app.get("summary", "")),
        "description": str(app.get("description", "")),
        "features": [str(item) for item in features],
        "tags": [str(item) for item in tags],
        "entrypoint": str(app.get("entrypoint", "")),
        "size": str(app.get("size", "")),
        "installed": bool(app.get("installed", False)),
        "source": str(app.get("source", source_id)),
    }


class CrixaStore(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Foundry")
        self.geometry("1240x780")
        self.minsize(1040, 660)
        self.configure(bg="#111418")

        self.backends: list[Backend] = []
        self.backend_map: dict[str, Backend] = {}
        self.all_apps: list[dict] = []
        self.filtered_apps: list[dict] = []
        self.category_buttons: dict[str, tk.Button] = {}

        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *_: self.refresh_apps_list())
        self.source_var = tk.StringVar(value=DEFAULT_BACKEND)
        self.source_label_var = tk.StringVar(value="")
        self.status_var = tk.StringVar(value="Foundry ready")
        self.selected_category = ALL_CATEGORIES

        self.setup_style()
        self.build_ui()
        self.set_status("Opening Foundry...")
        self.after(80, lambda: self.reload_backends(initial=True))

    def setup_style(self) -> None:
        self.style = ttk.Style(self)
        try:
            self.style.theme_use("clam")
        except tk.TclError:
            pass
        self.colors = {
            "bg": "#111418",
            "rail": "#171b20",
            "panel": "#1d242b",
            "panel_alt": "#222b33",
            "field": "#0f1216",
            "line": "#33404a",
            "accent": "#32c7b8",
            "accent_dark": "#1a7f78",
            "warm": "#f2b84b",
            "danger": "#d96565",
            "text": "#eef4f2",
            "muted": "#9aa9a8",
            "subtle": "#738280",
        }
        self.option_add("*Font", "Helvetica 10")
        self.option_add("*Entry.relief", "flat")
        self.style.configure(".", background=self.colors["bg"], foreground=self.colors["text"], font=("Helvetica", 10))
        self.style.configure("Surface.TFrame", background=self.colors["panel"])
        self.style.configure("SurfaceAlt.TFrame", background=self.colors["panel_alt"])
        self.style.configure("Rail.TFrame", background=self.colors["rail"])
        self.style.configure("Title.TLabel", background=self.colors["panel"], foreground=self.colors["text"], font=("Helvetica", 19, "bold"))
        self.style.configure("Section.TLabel", background=self.colors["panel"], foreground=self.colors["text"], font=("Helvetica", 11, "bold"))
        self.style.configure("Muted.TLabel", background=self.colors["panel"], foreground=self.colors["muted"])
        self.style.configure("RailMuted.TLabel", background=self.colors["rail"], foreground=self.colors["muted"])
        self.style.configure("TButton", padding=(12, 8))
        self.style.configure("Accent.TButton", padding=(14, 9))
        self.style.map("Accent.TButton", background=[("active", self.colors["accent_dark"])])
        self.style.configure(
            "Store.Treeview",
            background=self.colors["field"],
            fieldbackground=self.colors["field"],
            foreground=self.colors["text"],
            rowheight=34,
            borderwidth=0,
        )
        self.style.map("Store.Treeview", background=[("selected", self.colors["accent_dark"])], foreground=[("selected", "#ffffff")])
        self.style.configure("Store.Treeview.Heading", background=self.colors["panel_alt"], foreground=self.colors["text"], padding=(8, 8))

    def build_ui(self) -> None:
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        rail = ttk.Frame(self, style="Rail.TFrame")
        rail.grid(row=0, column=0, sticky="nsw")
        rail.grid_rowconfigure(4, weight=1)

        tk.Label(
            rail,
            text="Foundry",
            bg=self.colors["rail"],
            fg=self.colors["text"],
            font=("Helvetica", 21, "bold"),
        ).grid(row=0, column=0, sticky="w", padx=18, pady=(20, 4))
        tk.Label(
            rail,
            text="CRIXA app catalog",
            bg=self.colors["rail"],
            fg=self.colors["muted"],
        ).grid(row=1, column=0, sticky="w", padx=18, pady=(0, 18))

        self.source_combo = ttk.Combobox(rail, textvariable=self.source_label_var, state="readonly", width=27)
        self.source_combo.grid(row=2, column=0, sticky="ew", padx=18, pady=(0, 12))
        self.source_combo.bind("<<ComboboxSelected>>", lambda _e: self.refresh_apps_list())

        ttk.Label(rail, text="Browse", style="RailMuted.TLabel").grid(row=3, column=0, sticky="w", padx=18, pady=(2, 6))
        self.category_frame = ttk.Frame(rail, style="Rail.TFrame")
        self.category_frame.grid(row=4, column=0, sticky="nsew", padx=12, pady=(0, 12))

        rail_actions = ttk.Frame(rail, style="Rail.TFrame")
        rail_actions.grid(row=5, column=0, sticky="sew", padx=18, pady=(0, 18))
        ttk.Button(rail_actions, text="Upgrade Installed", command=self.upgrade_selected_backend).pack(fill="x", pady=(0, 8))
        ttk.Button(rail_actions, text="Backends", command=self.open_user_backend_folder).pack(fill="x", pady=(0, 8))
        ttk.Button(rail_actions, text="Reload", command=self.reload_backends).pack(fill="x")

        main = ttk.Frame(self, style="Surface.TFrame")
        main.grid(row=0, column=1, sticky="nsew", padx=(0, 14), pady=14)
        main.grid_columnconfigure(0, weight=1)
        main.grid_rowconfigure(2, weight=1)

        header = ttk.Frame(main, style="Surface.TFrame")
        header.grid(row=0, column=0, sticky="ew", padx=18, pady=(18, 12))
        header.grid_columnconfigure(1, weight=1)
        ttk.Label(header, text="Software", style="Title.TLabel").grid(row=0, column=0, sticky="w")
        search = tk.Entry(
            header,
            textvariable=self.search_var,
            bg=self.colors["field"],
            fg=self.colors["text"],
            insertbackground=self.colors["text"],
            relief="flat",
            highlightthickness=1,
            highlightbackground=self.colors["line"],
            highlightcolor=self.colors["accent"],
            font=("Helvetica", 11),
        )
        search.grid(row=0, column=1, sticky="ew", padx=(18, 0), ipady=8)

        self.hero = tk.Frame(main, bg=self.colors["panel_alt"], highlightthickness=1, highlightbackground=self.colors["line"])
        self.hero.grid(row=1, column=0, sticky="ew", padx=18, pady=(0, 12))
        self.hero.grid_columnconfigure(0, weight=1)
        self.hero_title = tk.Label(self.hero, text="Curated CRIXA Apps", bg=self.colors["panel_alt"], fg=self.colors["text"], font=("Helvetica", 15, "bold"))
        self.hero_title.grid(row=0, column=0, sticky="w", padx=14, pady=(12, 2))
        self.hero_copy = tk.Label(self.hero, text="", bg=self.colors["panel_alt"], fg=self.colors["muted"], justify="left")
        self.hero_copy.grid(row=1, column=0, sticky="w", padx=14, pady=(0, 12))
        self.hero_stats = tk.Label(self.hero, text="", bg=self.colors["panel_alt"], fg=self.colors["warm"], font=("Helvetica", 10, "bold"))
        self.hero_stats.grid(row=0, column=1, rowspan=2, sticky="e", padx=14, pady=12)

        body = ttk.Frame(main, style="Surface.TFrame")
        body.grid(row=2, column=0, sticky="nsew", padx=18, pady=(0, 12))
        body.grid_columnconfigure(0, weight=2)
        body.grid_columnconfigure(1, weight=1)
        body.grid_rowconfigure(0, weight=1)

        list_panel = ttk.Frame(body, style="SurfaceAlt.TFrame")
        list_panel.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        list_panel.grid_columnconfigure(0, weight=1)
        list_panel.grid_rowconfigure(1, weight=1)
        self.count_label = ttk.Label(list_panel, text="0 apps", style="Muted.TLabel")
        self.count_label.grid(row=0, column=0, sticky="w", padx=12, pady=(12, 8))

        columns = ("status", "name", "category", "version", "size")
        self.apps_tree = ttk.Treeview(list_panel, columns=columns, show="headings", style="Store.Treeview", selectmode="browse")
        for key, label, width in (
            ("status", "", 32),
            ("name", "Application", 230),
            ("category", "Category", 120),
            ("version", "Version", 78),
            ("size", "Size", 78),
        ):
            self.apps_tree.heading(key, text=label)
            self.apps_tree.column(key, width=width, minwidth=width if key != "name" else 180, stretch=key == "name")
        self.apps_tree.grid(row=1, column=0, sticky="nsew", padx=12, pady=(0, 12))
        self.apps_tree.bind("<<TreeviewSelect>>", lambda _e: self.on_select())
        self.apps_tree.bind("<Double-Button-1>", lambda _e: self.launch_or_install_selected())

        detail = ttk.Frame(body, style="SurfaceAlt.TFrame")
        detail.grid(row=0, column=1, sticky="nsew")
        detail.grid_columnconfigure(0, weight=1)
        detail.grid_rowconfigure(3, weight=1)

        self.title_var = tk.StringVar(value="Select an app")
        self.meta_var = tk.StringVar(value="")
        ttk.Label(detail, textvariable=self.title_var, style="Title.TLabel").grid(row=0, column=0, sticky="w", padx=14, pady=(14, 2))
        ttk.Label(detail, textvariable=self.meta_var, style="Muted.TLabel").grid(row=1, column=0, sticky="w", padx=14, pady=(0, 10))

        self.tag_line = tk.Label(detail, text="", bg=self.colors["panel_alt"], fg=self.colors["warm"], justify="left", wraplength=350)
        self.tag_line.grid(row=2, column=0, sticky="ew", padx=14, pady=(0, 8))

        self.details_text = tk.Text(
            detail,
            wrap="word",
            bg=self.colors["field"],
            fg=self.colors["text"],
            relief="flat",
            highlightthickness=1,
            highlightbackground=self.colors["line"],
            padx=12,
            pady=12,
            font=("Helvetica", 10),
        )
        self.details_text.grid(row=3, column=0, sticky="nsew", padx=14, pady=(0, 12))
        self.details_text.configure(state="disabled")

        actions = ttk.Frame(detail, style="SurfaceAlt.TFrame")
        actions.grid(row=4, column=0, sticky="ew", padx=14, pady=(0, 14))
        self.install_btn = ttk.Button(actions, text="Install", style="Accent.TButton", command=self.install_selected)
        self.install_btn.pack(side="left", padx=(0, 8))
        self.launch_btn = ttk.Button(actions, text="Launch", command=self.launch_selected)
        self.launch_btn.pack(side="left", padx=8)
        self.remove_btn = ttk.Button(actions, text="Remove", command=self.remove_selected)
        self.remove_btn.pack(side="left", padx=8)
        ttk.Button(actions, text="Close", command=self.destroy).pack(side="right")

        ttk.Label(main, textvariable=self.status_var, style="Muted.TLabel").grid(row=3, column=0, sticky="ew", padx=20, pady=(0, 14))

    def set_status(self, text: str) -> None:
        self.status_var.set(text)

    def command_for_manifest(self, manifest: dict, manifest_path: Path) -> list[str]:
        command_raw = str(manifest.get("command", "")).strip()
        if not command_raw:
            return []
        command_path = Path(command_raw)
        if DEV_ROOT is not None and command_path.is_absolute() and not command_path.exists():
            local_backend = DEV_ROOT / "store-backends" / command_path.name
            if local_backend.exists():
                command_path = local_backend
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
        if DEV_BACKEND_DIR is not None:
            search_dirs.append(DEV_BACKEND_DIR)
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
                backends.append(
                    Backend(
                        backend_id=backend_id,
                        name=name,
                        command=command,
                        supports_upgrade=bool(manifest.get("supports_upgrade", True)),
                        priority=int(manifest.get("priority", 100)),
                        description=str(manifest.get("description", "")).strip(),
                        manifest_path=manifest_path,
                    )
                )
                discovered_ids.add(backend_id)
        return sorted(backends, key=lambda row: (row.priority, row.name.lower()))

    def selected_backend(self) -> Backend | None:
        return self.backend_map.get(self.source_var.get().strip())

    def call_backend(self, backend: Backend, payload: dict, timeout_sec: int = 45) -> tuple[bool, dict]:
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
            self.all_apps = []
            self.filtered_apps = []
            self.refresh_category_buttons()
            self.render_apps()
            self.load_builtin_catalog("No store backends found. Showing bundled catalog.")
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

    def refresh_category_buttons(self) -> None:
        for child in self.category_frame.winfo_children():
            child.destroy()
        self.category_buttons.clear()
        categories = [ALL_CATEGORIES, INSTALLED_CATEGORY]
        categories.extend(sorted({app.get("category", "General") for app in self.all_apps}))
        seen: set[str] = set()
        unique = []
        for item in categories:
            if item not in seen:
                unique.append(item)
                seen.add(item)
        if self.selected_category not in seen:
            self.selected_category = ALL_CATEGORIES
        for idx, category in enumerate(unique):
            count = len(self.apps_for_category(category))
            text = f"{category}  {count}"
            active = category == self.selected_category
            btn = tk.Button(
                self.category_frame,
                text=text,
                command=lambda cat=category: self.select_category(cat),
                anchor="w",
                relief="flat",
                bd=0,
                bg=self.colors["accent_dark"] if active else self.colors["rail"],
                fg="#ffffff" if active else self.colors["muted"],
                activebackground=self.colors["accent_dark"],
                activeforeground="#ffffff",
                padx=12,
                pady=8,
            )
            btn.grid(row=idx, column=0, sticky="ew", pady=1)
            self.category_buttons[category] = btn

    def apps_for_category(self, category: str) -> list[dict]:
        if category == ALL_CATEGORIES:
            return list(self.all_apps)
        if category == INSTALLED_CATEGORY:
            return [app for app in self.all_apps if app.get("installed")]
        return [app for app in self.all_apps if app.get("category") == category]

    def select_category(self, category: str) -> None:
        self.selected_category = category
        self.refresh_category_buttons()
        self.render_apps()

    def selected_app(self) -> dict | None:
        selected = self.apps_tree.selection()
        if not selected:
            return None
        app_id = str(selected[0])
        for app in self.filtered_apps:
            if app.get("id") == app_id:
                return app
        return None

    def refresh_apps_list(self, selected_id: str | None = None) -> None:
        self.normalize_source_combo_selection()
        backend = self.selected_backend()
        if backend is None:
            self.all_apps = []
            self.filtered_apps = []
            self.refresh_category_buttons()
            self.render_apps()
            self.load_builtin_catalog("No backend selected. Showing bundled catalog.")
            return
        ok, payload = self.call_backend(backend, {"action": "list", "query": "", "limit": 500}, timeout_sec=12)
        if not ok:
            self.load_builtin_catalog(payload.get("error", "Backend query failed"))
            return
        apps = payload.get("apps", [])
        if not isinstance(apps, list):
            apps = []
        self.all_apps = [ensure_app_shape(item, backend.backend_id) for item in apps if isinstance(item, dict)]
        self.refresh_category_buttons()
        self.render_apps(selected_id=selected_id)
        self.set_status(payload.get("message", "") or f"Loaded {len(self.all_apps)} app(s) from {backend.name}")

    def catalog_paths(self) -> list[Path]:
        paths = [SYSTEM_CATALOG_PATH]
        if DEV_CATALOG_PATH is not None:
            paths.append(DEV_CATALOG_PATH)
        return paths

    def load_builtin_catalog(self, reason: str) -> None:
        catalog_apps: list[dict] = []
        for path in self.catalog_paths():
            if not path.exists():
                continue
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            raw_apps = payload.get("apps", [])
            if isinstance(raw_apps, list):
                catalog_apps = [ensure_app_shape(item, "bundled") for item in raw_apps if isinstance(item, dict)]
                break
        self.all_apps = catalog_apps
        self.filtered_apps = []
        self.refresh_category_buttons()
        self.render_apps()
        if catalog_apps:
            self.set_status(f"{reason} Bundled catalog is available; install actions need the CRIXA backend.")
        else:
            self.set_status(f"{reason} No bundled catalog was found.")

    def render_apps(self, selected_id: str | None = None) -> None:
        query = self.search_var.get().strip().lower()
        apps = self.apps_for_category(self.selected_category)
        if query:
            apps = [
                app
                for app in apps
                if query
                in " ".join(
                    [
                        app.get("id", ""),
                        app.get("name", ""),
                        app.get("category", ""),
                        app.get("summary", ""),
                        app.get("description", ""),
                        " ".join(app.get("features", [])),
                        " ".join(app.get("tags", [])),
                    ]
                ).lower()
            ]
        self.filtered_apps = sorted(apps, key=lambda row: (not row.get("installed"), row.get("name", "").lower()))
        self.apps_tree.delete(*self.apps_tree.get_children())
        installed_count = len([app for app in self.all_apps if app.get("installed")])
        for app in self.filtered_apps:
            marker = "✓" if app.get("installed") else ""
            self.apps_tree.insert(
                "",
                "end",
                iid=app.get("id", ""),
                values=(marker, app.get("name", ""), app.get("category", ""), app.get("version", ""), app.get("size", "")),
            )
        self.count_label.configure(text=f"{len(self.filtered_apps)} shown  |  {installed_count} installed")
        categories = len({app.get("category", "General") for app in self.all_apps})
        self.hero_copy.configure(text=f"{self.selected_category} apps from the selected source. Search, install, launch, update, or remove packages.")
        self.hero_stats.configure(text=f"{len(self.all_apps)} apps\n{categories} categories")
        if selected_id and selected_id in [app.get("id") for app in self.filtered_apps]:
            self.apps_tree.selection_set(selected_id)
            self.apps_tree.focus(selected_id)
        elif self.filtered_apps:
            first_id = self.filtered_apps[0].get("id", "")
            self.apps_tree.selection_set(first_id)
            self.apps_tree.focus(first_id)
        self.on_select()

    def on_select(self) -> None:
        backend = self.selected_backend()
        app = self.selected_app()
        if not app or backend is None:
            self.title_var.set("Select an app")
            self.meta_var.set("")
            self.tag_line.configure(text="")
            self.update_details("")
            for button in (self.install_btn, self.remove_btn, self.launch_btn):
                button.configure(state="disabled")
            return
        app_id = app.get("id", "")
        installed = bool(app.get("installed", False))
        self.title_var.set(app.get("name", app_id))
        self.meta_var.set(f"{app.get('category', 'General')}  |  Version {app.get('version', 'n/a')}  |  {app.get('size', '')}")
        tags = app.get("tags", [])
        self.tag_line.configure(text="  ".join(f"#{tag}" for tag in tags[:8]))
        features = app.get("features", [])
        feature_lines = "\n".join(f"  * {item}" for item in features) if features else "  * No feature list provided"
        details = (
            f"{app.get('summary', '')}\n\n"
            f"{app.get('description', '')}\n\n"
            f"Package: {app_id}\n"
            f"Source: {backend.name}\n"
            f"Entrypoint: {app.get('entrypoint', '') or 'n/a'}\n\n"
            f"Highlights\n{feature_lines}"
        )
        self.update_details(details)
        self.install_btn.configure(text="Update" if installed else "Install", state="normal")
        self.remove_btn.configure(state="normal" if installed else "disabled")
        self.launch_btn.configure(state="normal" if installed else "disabled")

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
        timeout_sec = 1800 if action in ("install", "remove") else 30
        ok, payload = self.call_backend(
            backend,
            {"action": action, "app_id": app.get("id", ""), "force": force},
            timeout_sec=timeout_sec,
        )
        if ok:
            return True, payload.get("message", "") or f"{action} completed"
        return False, payload.get("error", "backend action failed")

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
        if not app or not app.get("installed"):
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

    def launch_or_install_selected(self) -> None:
        app = self.selected_app()
        if not app:
            return
        if app.get("installed"):
            self.launch_selected()
        else:
            self.install_selected()

    def upgrade_selected_backend(self) -> None:
        backend = self.selected_backend()
        if backend is None:
            return
        if not backend.supports_upgrade:
            messagebox.showinfo("Foundry", "Selected backend does not support bulk upgrade.")
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
            subprocess.Popen(["crixa-files", str(path)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            pass


def main() -> int:
    app = CrixaStore()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
