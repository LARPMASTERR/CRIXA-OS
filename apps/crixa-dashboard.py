#!/usr/bin/env python3
from __future__ import annotations

import configparser
import os
import shlex
import subprocess
import sys
import tkinter as tk
from tkinter import messagebox
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

DESKTOP_DIRS = [
    Path.home() / ".local" / "share" / "applications",
    Path("/usr/local/share/applications"),
    Path("/usr/share/applications"),
]

FEATURED_IDS = [
    "crixa-browser.desktop",
    "crixa-files.desktop",
    "crixa-terminal.desktop",
    "crixa-store.desktop",
    "crixa-settings.desktop",
    "crixa-updater.desktop",
]

SYSTEM_ACTIONS = [
    ("Bridge", "System controls, appearance, and hardware settings", ["crixa-settings"]),
    ("Foundry", "Install or remove CRIXA-curated applications", ["crixa-store"]),
    ("Pulse", "Inspect processes, services, and live system load", ["crixa-task-manager"]),
    ("Transit", "Manage updates, tracks, and rollback snapshots", ["crixa-updater"]),
    ("Backdrop", "Browse the installed wallpaper collection", ["crixa-files", "/usr/share/backgrounds/crixa"]),
]

POWER_ACTIONS = [
    ("Lock", "Lock this session", ["loginctl", "lock-session"]),
    ("Sleep", "Suspend the system", ["systemctl", "suspend"]),
    ("Restart", "Reboot now", ["systemctl", "reboot"]),
    ("Power Off", "Shut the system down", ["systemctl", "poweroff"]),
]

DEV_ROOT = Path(__file__).resolve().parents[1] if Path(__file__).resolve().parent.name == "apps" else None


@dataclass(slots=True)
class DesktopApp:
    desktop_id: str
    name: str
    comment: str
    exec_line: str
    path: Path


def _desktop_dirs() -> list[Path]:
    dirs: list[Path] = []
    for path in DESKTOP_DIRS:
        if path.exists():
            dirs.append(path)
    return dirs


def _bool_value(raw: str) -> bool:
    return raw.strip().lower() in {"1", "true", "yes"}


def _load_desktop_file(path: Path) -> DesktopApp | None:
    parser = configparser.ConfigParser(interpolation=None, strict=False)
    parser.optionxform = str
    try:
        with path.open("r", encoding="utf-8") as handle:
            parser.read_file(handle)
    except Exception:
        return None

    if "Desktop Entry" not in parser:
        return None

    entry = parser["Desktop Entry"]
    if entry.get("Type", "").strip() != "Application":
        return None
    if _bool_value(entry.get("NoDisplay", "false")):
        return None
    if _bool_value(entry.get("Hidden", "false")):
        return None

    name = entry.get("Name", "").strip()
    exec_line = entry.get("Exec", "").strip()
    if not name or not exec_line:
        return None

    return DesktopApp(
        desktop_id=path.name,
        name=name,
        comment=entry.get("Comment", "").strip(),
        exec_line=exec_line,
        path=path,
    )


def load_apps() -> list[DesktopApp]:
    discovered: dict[str, DesktopApp] = {}
    for directory in _desktop_dirs():
        for path in sorted(directory.glob("*.desktop")):
            app = _load_desktop_file(path)
            if app and app.desktop_id not in discovered:
                discovered[app.desktop_id] = app
    return sorted(discovered.values(), key=lambda app: app.name.lower())


def desktop_exec_fallback(exec_line: str) -> list[str]:
    command: list[str] = []
    for token in shlex.split(exec_line):
        if token.startswith("%"):
            continue
        if "%" in token:
            token = token.replace("%%", "%")
            if "%" in token:
                continue
        command.append(token)
    return command


class OrbitDashboard(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Orbit")
        self.configure(bg="#050a11")

        self.apps = load_apps()
        self.app_map = {app.desktop_id: app for app in self.apps}
        self.filtered_apps: list[DesktopApp] = []

        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *_: self.refresh_results())
        self.clock_var = tk.StringVar()
        self.date_var = tk.StringVar()
        self.summary_var = tk.StringVar()

        self.palette = {
            "overlay": "#080a0d",
            "shell": "#111418",
            "surface": "#191f24",
            "surface_alt": "#20282e",
            "surface_soft": "#26323a",
            "stroke": "#34424a",
            "stroke_bright": "#4b626d",
            "accent": "#35c9ba",
            "accent_soft": "#1d706a",
            "text": "#eef4f2",
            "muted": "#a3b1af",
            "subtle": "#7f8f8d",
            "warm": "#f2b84b",
        }

        self._configure_window()
        self._build_shell()
        self._tick_clock()
        self.refresh_results()
        self.after(50, self._focus_search)

    def _set_surface_state(self, widgets: list[tk.Widget], background: str) -> None:
        for widget in widgets:
            try:
                widget.configure(bg=background)
            except tk.TclError:
                continue

    def _bind_click_tree(
        self,
        widget: tk.Widget,
        launch,
        hover_widgets: list[tk.Widget],
        normal_bg: str,
        hover_bg: str,
    ) -> None:
        widget.bind("<Button-1>", launch)
        widget.bind("<Enter>", lambda _event, target=hover_widgets: self._set_surface_state(target, hover_bg))
        widget.bind("<Leave>", lambda _event, target=hover_widgets: self._set_surface_state(target, normal_bg))
        for child in widget.winfo_children():
            self._bind_click_tree(child, launch, hover_widgets, normal_bg, hover_bg)

    def _configure_window(self) -> None:
        self.overrideredirect(True)
        self.attributes("-topmost", True)
        try:
            self.wm_attributes("-type", "dialog")
        except tk.TclError:
            pass

        self.bind("<Escape>", lambda _event: self.close())
        self.bind("<Return>", self._launch_default_selection)
        self.bind("<Down>", lambda _event: self._move_results(1))
        self.bind("<Up>", lambda _event: self._move_results(-1))

    def _build_shell(self) -> None:
        screen_w = self.winfo_screenwidth()
        screen_h = self.winfo_screenheight()
        self.compact = screen_w < 1180
        shell_w = min(1480, max(760, screen_w - 72))
        shell_h = min(900, max(600, screen_h - 72))
        if shell_w > screen_w - 32:
            shell_w = max(720, screen_w - 32)
        if shell_h > screen_h - 32:
            shell_h = max(560, screen_h - 32)
        self.shell_w = shell_w
        self.shell_h = shell_h
        self.content_wrap = max(180, min(560, int(shell_w * 0.42)))
        self.card_wrap = 190 if self.compact else 250

        x = max(12, (screen_w - shell_w) // 2)
        y = max(12, (screen_h - shell_h) // 2)
        self.geometry(f"{shell_w}x{shell_h}+{x}+{y}")

        self.shell = tk.Frame(
            self,
            bg=self.palette["shell"],
            highlightbackground=self.palette["stroke_bright"],
            highlightcolor=self.palette["stroke_bright"],
            highlightthickness=1,
            bd=0,
        )
        self.shell.pack(fill="both", expand=True)
        self.shell.grid_columnconfigure(1, weight=1)
        self.shell.grid_rowconfigure(1, weight=1)

        header = tk.Frame(self.shell, bg=self.palette["surface"], height=104)
        header.grid(row=0, column=0, columnspan=3, sticky="ew", padx=16, pady=(16, 10))
        header.grid_columnconfigure(1, weight=1)
        header.grid_propagate(False)

        brand = tk.Frame(header, bg=self.palette["surface"])
        brand.grid(row=0, column=0, sticky="nsw", padx=(18, 16), pady=16)

        tk.Label(
            brand,
            text="Orbit",
            bg=self.palette["surface"],
            fg=self.palette["text"],
            font=("Helvetica", 22, "bold"),
        ).pack(anchor="w")
        tk.Label(
            brand,
            text="Search, launch, and steer the system from one dashboard.",
            bg=self.palette["surface"],
            fg=self.palette["muted"],
            font=("Helvetica", 9),
        ).pack(anchor="w", pady=(4, 0))

        search_wrap = tk.Frame(
            header,
            bg=self.palette["surface_alt"],
            highlightbackground=self.palette["stroke"],
            highlightthickness=1,
        )
        search_wrap.grid(row=0, column=1, sticky="ew", padx=(0, 14), pady=18)
        search_wrap.grid_columnconfigure(0, weight=1)

        self.search_entry = tk.Entry(
            search_wrap,
            textvariable=self.search_var,
            relief="flat",
            bd=0,
            bg=self.palette["surface_alt"],
            fg=self.palette["text"],
            insertbackground=self.palette["accent"],
            selectbackground=self.palette["accent_soft"],
            selectforeground=self.palette["text"],
            font=("Helvetica", 13),
        )
        self.search_entry.grid(row=0, column=0, sticky="ew", padx=14, pady=10)

        header_meta = tk.Frame(header, bg=self.palette["surface"])
        header_meta.grid(row=0, column=2, sticky="nse", padx=(0, 18), pady=16)
        tk.Label(
            header_meta,
            textvariable=self.clock_var,
            bg=self.palette["surface"],
            fg=self.palette["text"],
            font=("Helvetica", 15, "bold"),
        ).pack(anchor="e")
        tk.Label(
            header_meta,
            textvariable=self.date_var,
            bg=self.palette["surface"],
            fg=self.palette["muted"],
            font=("Helvetica", 8),
        ).pack(anchor="e", pady=(2, 0))

        rail_width = 224 if self.compact else 262
        results_width = 250 if self.compact else 320

        rail = tk.Frame(self.shell, bg=self.palette["surface"], width=rail_width)
        rail.grid(row=1, column=0, sticky="nsew", padx=(16, 10), pady=(0, 16))
        rail.grid_propagate(False)

        main = tk.Frame(self.shell, bg=self.palette["shell"])
        main.grid(row=1, column=1, sticky="nsew", pady=(0, 16))
        main.grid_columnconfigure(0, weight=1)
        main.grid_rowconfigure(1, weight=1)

        results = tk.Frame(self.shell, bg=self.palette["surface"], width=results_width)
        results.grid(row=1, column=2, sticky="nsew", padx=(10, 16), pady=(0, 16))
        results.grid_propagate(False)
        results.grid_columnconfigure(0, weight=1)
        results.grid_rowconfigure(1, weight=1)

        self._build_left_rail(rail)
        self._build_feature_grid(main)
        self._build_results_pane(results)

    def _build_left_rail(self, rail: tk.Frame) -> None:
        hero = tk.Frame(rail, bg=self.palette["surface_alt"], highlightbackground=self.palette["stroke"], highlightthickness=1)
        hero.pack(fill="x", padx=18, pady=(18, 14))

        tk.Frame(hero, bg=self.palette["accent"], height=3).pack(fill="x")
        tk.Label(
            hero,
            text="System Ready",
            bg=self.palette["surface_alt"],
            fg=self.palette["text"],
            font=("Helvetica", 13, "bold"),
        ).pack(anchor="w", padx=16, pady=(16, 4))
        tk.Label(
            hero,
            text="CRIXA is ready. Launch apps, settings, updates, and power controls from here.",
            bg=self.palette["surface_alt"],
            fg=self.palette["muted"],
            justify="left",
            wraplength=185 if self.compact else 210,
            font=("Helvetica", 9),
        ).pack(anchor="w", padx=16, pady=(0, 14))

        session_label = f"Session: {os.environ.get('XDG_SESSION_TYPE', 'plasma').upper()}"
        tk.Label(
            hero,
            text=session_label,
            bg=self.palette["surface_alt"],
            fg=self.palette["subtle"],
            font=("Courier", 8),
        ).pack(anchor="w", padx=16, pady=(0, 16))

        tk.Label(
            rail,
            text="Control Surface",
            bg=self.palette["surface"],
            fg=self.palette["muted"],
            font=("Helvetica", 9, "bold"),
        ).pack(anchor="w", padx=18)

        for title, subtitle, command in SYSTEM_ACTIONS:
            self._action_button(rail, title, subtitle, command).pack(fill="x", padx=18, pady=(8, 0))

    def _build_feature_grid(self, main: tk.Frame) -> None:
        header = tk.Frame(main, bg=self.palette["shell"])
        header.grid(row=0, column=0, sticky="ew", pady=(0, 14))
        header.grid_columnconfigure(0, weight=1)

        tk.Label(
            header,
            text="Launch Deck",
            bg=self.palette["shell"],
            fg=self.palette["text"],
            font=("Helvetica", 16, "bold"),
        ).grid(row=0, column=0, sticky="w")
        tk.Label(
            header,
            text="Pinned tools and daily drivers",
            bg=self.palette["shell"],
            fg=self.palette["muted"],
            font=("Helvetica", 9),
        ).grid(row=1, column=0, sticky="w", pady=(4, 0))

        grid = tk.Frame(main, bg=self.palette["shell"])
        grid.grid(row=1, column=0, sticky="nsew")
        columns = 2 if self.compact else 3
        for column in range(columns):
            grid.grid_columnconfigure(column, weight=1, uniform="cards")

        for index, desktop_id in enumerate(FEATURED_IDS):
            app = self.app_map.get(desktop_id)
            if not app:
                continue
            row = index // columns
            column = index % columns
            card = self._feature_card(grid, app)
            card.grid(row=row, column=column, sticky="nsew", padx=(0 if column == 0 else 8, 8 if column < columns - 1 else 0), pady=(0, 10))
            grid.grid_rowconfigure(row, weight=1, uniform="cardrows")

        footer = tk.Frame(main, bg=self.palette["surface"], highlightbackground=self.palette["stroke"], highlightthickness=1)
        footer.grid(row=2, column=0, sticky="ew", pady=(10, 0))
        tk.Label(
            footer,
            text="Hints",
            bg=self.palette["surface"],
            fg=self.palette["muted"],
            font=("Helvetica", 9, "bold"),
        ).pack(anchor="w", padx=16, pady=(12, 2))
        tk.Label(
            footer,
            text="Type to filter installed applications. Press Enter to launch the first result. Press Esc anywhere to close Orbit.",
            bg=self.palette["surface"],
            fg=self.palette["subtle"],
            justify="left",
            wraplength=self.content_wrap,
            font=("Helvetica", 9),
        ).pack(anchor="w", padx=16, pady=(0, 14))

    def _build_results_pane(self, pane: tk.Frame) -> None:
        tk.Label(
            pane,
            text="Index",
            bg=self.palette["surface"],
            fg=self.palette["text"],
            font=("Helvetica", 14, "bold"),
        ).grid(row=0, column=0, sticky="w", padx=18, pady=(18, 2))
        tk.Label(
            pane,
            textvariable=self.summary_var,
            bg=self.palette["surface"],
            fg=self.palette["muted"],
            font=("Helvetica", 8),
        ).grid(row=0, column=0, sticky="w", padx=18, pady=(44, 12))

        self.results_list = tk.Listbox(
            pane,
            activestyle="none",
            bg=self.palette["surface_alt"],
            fg=self.palette["text"],
            selectbackground=self.palette["accent_soft"],
            selectforeground=self.palette["text"],
            relief="flat",
            bd=0,
            highlightthickness=0,
            font=("Helvetica", 9),
        )
        self.results_list.grid(row=1, column=0, sticky="nsew", padx=18, pady=(0, 14))
        self.results_list.bind("<Double-Button-1>", self._launch_selected_result)
        self.results_list.bind("<Return>", self._launch_selected_result)

        power = tk.Frame(pane, bg=self.palette["surface"])
        power.grid(row=2, column=0, sticky="ew", padx=18, pady=(0, 18))

        tk.Label(
            power,
            text="Power",
            bg=self.palette["surface"],
            fg=self.palette["muted"],
            font=("Helvetica", 9, "bold"),
        ).pack(anchor="w", pady=(0, 8))

        for title, subtitle, command in POWER_ACTIONS:
            button = self._action_button(power, title, subtitle, command, compact=True)
            button.pack(fill="x", pady=(0, 8))

    def _action_button(
        self,
        parent: tk.Misc,
        title: str,
        subtitle: str,
        command: list[str],
        compact: bool = False,
    ) -> tk.Frame:
        frame = tk.Frame(parent, bg=self.palette["surface_alt"], highlightbackground=self.palette["stroke"], highlightthickness=1, cursor="hand2")

        accent = tk.Frame(frame, bg=self.palette["accent"], width=3)
        accent.pack(side="left", fill="y")

        body = tk.Frame(frame, bg=self.palette["surface_alt"])
        body.pack(side="left", fill="both", expand=True, padx=12, pady=(10 if compact else 12))

        title_label = tk.Label(
            body,
            text=title,
            bg=self.palette["surface_alt"],
            fg=self.palette["text"],
            font=("Helvetica", 9 if compact else 10, "bold"),
        )
        title_label.pack(anchor="w")
        subtitle_label = tk.Label(
            body,
            text=subtitle,
            bg=self.palette["surface_alt"],
            fg=self.palette["muted"],
            justify="left",
            wraplength=190 if compact else 205,
            font=("Helvetica", 8),
        )
        subtitle_label.pack(anchor="w", pady=(3, 0))

        def launch(_event: tk.Event[tk.Misc] | None = None) -> None:
            self.run_command(command)

        surface_widgets = [frame, body, title_label, subtitle_label]
        self._bind_click_tree(frame, launch, surface_widgets, self.palette["surface_alt"], self.palette["surface_soft"])
        return frame

    def _feature_card(self, parent: tk.Frame, app: DesktopApp) -> tk.Frame:
        frame = tk.Frame(parent, bg=self.palette["surface"], highlightbackground=self.palette["stroke"], highlightthickness=1, cursor="hand2")
        frame.grid_columnconfigure(0, weight=1)
        tk.Frame(frame, bg=self.palette["accent"], height=3).grid(row=0, column=0, sticky="ew")

        name = tk.Label(
            frame,
            text=app.name,
            bg=self.palette["surface"],
            fg=self.palette["text"],
            font=("Helvetica", 11 if self.compact else 12, "bold"),
        )
        name.grid(row=1, column=0, sticky="w", padx=16, pady=(16, 4))

        summary = tk.Label(
            frame,
            text=app.comment or "Launch application",
            bg=self.palette["surface"],
            fg=self.palette["muted"],
            justify="left",
            wraplength=self.card_wrap,
            font=("Helvetica", 8 if self.compact else 9),
        )
        summary.grid(row=2, column=0, sticky="w", padx=16, pady=(0, 14))

        launch_hint = tk.Label(
            frame,
            text="Launch",
            bg=self.palette["surface"],
            fg=self.palette["subtle"],
            font=("Courier", 8),
        )
        launch_hint.grid(row=3, column=0, sticky="w", padx=16, pady=(0, 16))

        def launch(_event: tk.Event[tk.Misc] | None = None) -> None:
            self.launch_app(app)

        surface_widgets = [frame, name, summary, launch_hint]
        for widget in surface_widgets:
            widget.bind("<Button-1>", launch)
            widget.bind("<Enter>", lambda _event, target=surface_widgets: self._set_surface_state(target, self.palette["surface_alt"]))
            widget.bind("<Leave>", lambda _event, target=surface_widgets: self._set_surface_state(target, self.palette["surface"]))
        return frame

    def _focus_search(self) -> None:
        self.search_entry.focus_set()
        self.search_entry.icursor("end")

    def _tick_clock(self) -> None:
        now = datetime.now()
        self.clock_var.set(now.strftime("%H:%M"))
        self.date_var.set(now.strftime("%A, %B %d"))
        self.after(1000, self._tick_clock)

    def refresh_results(self) -> None:
        query = self.search_var.get().strip().lower()
        if not query:
            curated = [self.app_map[app_id] for app_id in FEATURED_IDS if app_id in self.app_map]
            curated_ids = {app.desktop_id for app in curated}
            extras = [app for app in self.apps if app.desktop_id not in curated_ids][:18]
            self.filtered_apps = curated + extras
            self.summary_var.set(f"{len(self.apps)} applications indexed")
        else:
            self.filtered_apps = [
                app
                for app in self.apps
                if query in app.name.lower() or query in app.comment.lower() or query in app.desktop_id.lower()
            ][:40]
            self.summary_var.set(f"{len(self.filtered_apps)} matches for “{query}”")

        self.results_list.delete(0, "end")
        for app in self.filtered_apps:
            label = app.name
            if app.comment:
                max_comment = 34 if self.compact else 48
                comment = app.comment
                if len(comment) > max_comment:
                    comment = comment[: max_comment - 1].rstrip() + "..."
                label += f"  -  {comment}"
            self.results_list.insert("end", label)

        if self.filtered_apps:
            self.results_list.selection_clear(0, "end")
            self.results_list.selection_set(0)
            self.results_list.activate(0)

    def _move_results(self, delta: int) -> None:
        if not self.filtered_apps:
            return
        current = self.results_list.curselection()
        index = current[0] if current else 0
        index = max(0, min(len(self.filtered_apps) - 1, index + delta))
        self.results_list.selection_clear(0, "end")
        self.results_list.selection_set(index)
        self.results_list.activate(index)
        self.results_list.see(index)

    def _launch_default_selection(self, _event: tk.Event[tk.Misc] | None = None) -> str:
        current = self.results_list.curselection()
        if current:
            self.launch_app(self.filtered_apps[current[0]])
            return "break"
        if self.filtered_apps:
            self.launch_app(self.filtered_apps[0])
            return "break"
        return "break"

    def _launch_selected_result(self, _event: tk.Event[tk.Misc] | None = None) -> str:
        current = self.results_list.curselection()
        if current:
            self.launch_app(self.filtered_apps[current[0]])
        return "break"

    def launch_app(self, app: DesktopApp) -> None:
        fallback = desktop_exec_fallback(app.exec_line)
        if fallback and self.run_command(fallback):
            return

        gio = shutil_which("gio")
        if gio and app.path.exists() and self.run_command([gio, "launch", str(app.path)]):
            return

        launcher = shutil_which("gtk-launch")
        if launcher:
            self.run_command([launcher, app.desktop_id.removesuffix(".desktop")])

    def run_command(self, command: list[str]) -> bool:
        if not command:
            return False
        env = os.environ.copy()
        extra_paths = [str(Path.home() / ".local" / "bin"), "/usr/local/bin", "/usr/bin", "/bin"]
        env["PATH"] = os.pathsep.join([*extra_paths, env.get("PATH", "")])
        executable = command[0]
        if "/" not in executable and shutil_which(executable, env.get("PATH", "")) is None:
            if executable == "crixa-store" and DEV_ROOT is not None:
                local_store = DEV_ROOT / "apps" / "crixa-store.py"
                if local_store.exists():
                    command = [sys.executable, str(local_store), *command[1:]]
                    executable = command[0]
                else:
                    messagebox.showerror("Orbit", f"Could not find command: {executable}")
                    return False
            else:
                messagebox.showerror("Orbit", f"Could not find command: {executable}")
                return False
        if "/" not in executable and shutil_which(executable, env.get("PATH", "")) is None:
            messagebox.showerror("Orbit", f"Could not find command: {executable}")
            return False
        try:
            subprocess.Popen(command, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
        except Exception as exc:
            messagebox.showerror("Orbit", f"Could not launch {command[0]}:\n{exc}")
            return False
        self.close()
        return True

    def close(self) -> None:
        self.destroy()


def shutil_which(program: str, path_value: str | None = None) -> str | None:
    for directory in (path_value or os.environ.get("PATH", "")).split(os.pathsep):
        if not directory:
            continue
        candidate = Path(directory) / program
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)
    return None


def main() -> int:
    app = OrbitDashboard()
    app.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
