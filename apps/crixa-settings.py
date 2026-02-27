#!/usr/bin/env python3
import os
import platform
import re
import subprocess
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

CONFIG_HOME = Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config")))
OPENBOX_AUTOSTART = CONFIG_HOME / "openbox" / "autostart"
OPENBOX_RC = CONFIG_HOME / "openbox" / "rc.xml"
TINT2_CFG = CONFIG_HOME / "tint2" / "tint2rc"
GTK_SETTINGS = CONFIG_HOME / "gtk-3.0" / "settings.ini"

FONT_PROFILES = {
    "Compact": {"gtk": 9, "panel": 8, "task": 8, "time1": 9, "time2": 7},
    "Comfortable": {"gtk": 10, "panel": 9, "task": 9, "time1": 10, "time2": 8},
    "Large": {"gtk": 11, "panel": 10, "task": 10, "time1": 11, "time2": 9},
}

PREFERRED_MODES = [
    "3440x1440",
    "2560x1440",
    "2560x1080",
    "1920x1200",
    "1920x1080",
    "1680x1050",
    "1600x900",
    "1366x768",
]

VIRT_PREFERRED_MODES = [
    "1600x900",
    "1366x768",
    "1920x1080",
    "1920x1200",
    "2560x1080",
    "3440x1440",
    "2560x1440",
    "1680x1050",
]


def run_cmd(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, capture_output=True, text=True)


def safe_read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""


def ensure_file(path: Path, default_text: str = "") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text(default_text, encoding="utf-8")


def is_virtualized() -> bool:
    result = run_cmd(["systemd-detect-virt", "-q"])
    return result.returncode == 0


class CrixaControlCenter(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("CRIXA Control Center")
        self.geometry("1180x760")
        self.minsize(980, 640)
        self.configure(bg="#081326")

        self._ensure_config_tree()
        self._configure_style()
        self._build_layout()
        self._load_state()
        self.show_page("Display")

    def _ensure_config_tree(self) -> None:
        ensure_file(TINT2_CFG)
        ensure_file(GTK_SETTINGS, "[Settings]\ngtk-theme-name=CRIXA\ngtk-font-name=DejaVu Sans 10\n")
        ensure_file(OPENBOX_AUTOSTART)
        ensure_file(OPENBOX_RC)

    def _configure_style(self) -> None:
        self.style = ttk.Style(self)
        try:
            self.style.theme_use("clam")
        except tk.TclError:
            pass

        self.colors = {
            "bg": "#081326",
            "surface": "#0d1c33",
            "surface_alt": "#122744",
            "nav": "#0b1a30",
            "accent": "#3d8cff",
            "fg": "#dbeafe",
            "muted": "#9db6da",
            "ok": "#7dd3fc",
            "warn": "#fbbf24",
        }

        self.style.configure(".", background=self.colors["bg"], foreground=self.colors["fg"], font=("DejaVu Sans", 10))
        self.style.configure("Surface.TFrame", background=self.colors["surface"])
        self.style.configure("Panel.TFrame", background=self.colors["surface_alt"])
        self.style.configure("Card.TLabelframe", background=self.colors["surface_alt"], foreground=self.colors["fg"])
        self.style.configure("Card.TLabelframe.Label", background=self.colors["surface_alt"], foreground=self.colors["fg"])
        self.style.configure(
            "TButton",
            background=self.colors["surface_alt"],
            foreground=self.colors["fg"],
            borderwidth=0,
            focusthickness=0,
            padding=(12, 8),
        )
        self.style.map("TButton", background=[("active", self.colors["accent"])], foreground=[("active", "#ffffff")])
        self.style.configure("TLabel", background=self.colors["surface"], foreground=self.colors["fg"])
        self.style.configure("Muted.TLabel", background=self.colors["surface"], foreground=self.colors["muted"])
        self.style.configure("Header.TLabel", font=("DejaVu Sans", 16, "bold"))
        self.style.configure("SubHeader.TLabel", font=("DejaVu Sans", 11))
        self.style.configure("TCheckbutton", background=self.colors["surface_alt"], foreground=self.colors["fg"])
        self.style.configure("TCombobox", fieldbackground="#0f2745", background="#0f2745", foreground=self.colors["fg"])
        self.style.map("TCombobox", fieldbackground=[("readonly", "#0f2745")], selectbackground=[("readonly", "#0f2745")])
        self.style.configure("Horizontal.TScale", background=self.colors["surface_alt"])

    def _build_layout(self) -> None:
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(1, weight=1)

        header = ttk.Frame(self, style="Surface.TFrame")
        header.grid(row=0, column=0, columnspan=2, sticky="nsew")
        header.grid_columnconfigure(0, weight=1)
        ttk.Label(header, text="CRIXA Control Center", style="Header.TLabel").grid(row=0, column=0, sticky="w", padx=20, pady=(14, 2))
        ttk.Label(
            header,
            text="Visuals, system toggles, startup behavior, and app launch tools",
            style="SubHeader.TLabel",
        ).grid(row=1, column=0, sticky="w", padx=20, pady=(0, 14))

        nav = tk.Frame(self, bg=self.colors["nav"], width=215)
        nav.grid(row=1, column=0, sticky="nsew")
        nav.grid_propagate(False)

        self.content = ttk.Frame(self, style="Surface.TFrame")
        self.content.grid(row=1, column=1, sticky="nsew")
        self.content.grid_columnconfigure(0, weight=1)
        self.content.grid_rowconfigure(0, weight=1)

        self.status_var = tk.StringVar(value="Ready")
        status = ttk.Label(self, textvariable=self.status_var, style="Muted.TLabel")
        status.grid(row=2, column=0, columnspan=2, sticky="ew", padx=16, pady=(6, 10))

        self.nav_buttons: dict[str, tk.Button] = {}
        for idx, page_name in enumerate(["Display", "Appearance", "Panel", "Startup", "Applications", "System", "About"]):
            btn = tk.Button(
                nav,
                text=page_name,
                command=lambda name=page_name: self.show_page(name),
                anchor="w",
                relief="flat",
                bd=0,
                highlightthickness=0,
                bg=self.colors["nav"],
                fg=self.colors["fg"],
                activebackground=self.colors["accent"],
                activeforeground="#ffffff",
                font=("DejaVu Sans", 11),
                padx=18,
                pady=12,
            )
            btn.pack(fill="x")
            if idx == 0:
                tk.Frame(nav, height=1, bg="#153358").pack(fill="x")
            self.nav_buttons[page_name] = btn

        self.pages: dict[str, ttk.Frame] = {}
        self.pages["Display"] = self._build_display_page()
        self.pages["Appearance"] = self._build_appearance_page()
        self.pages["Panel"] = self._build_panel_page()
        self.pages["Startup"] = self._build_startup_page()
        self.pages["Applications"] = self._build_apps_page()
        self.pages["System"] = self._build_system_page()
        self.pages["About"] = self._build_about_page()

        for page in self.pages.values():
            page.grid(row=0, column=0, sticky="nsew", padx=14, pady=14)

    def show_page(self, page_name: str) -> None:
        for name, btn in self.nav_buttons.items():
            if name == page_name:
                btn.configure(bg=self.colors["accent"], fg="#ffffff")
            else:
                btn.configure(bg=self.colors["nav"], fg=self.colors["fg"])
        self.pages[page_name].tkraise()
        self.set_status(f"{page_name} ready")
        if page_name == "Display":
            self.refresh_display_info()
        if page_name == "Appearance":
            self.refresh_wallpaper_label()

    def set_status(self, text: str, warning: bool = False) -> None:
        self.status_var.set(text)
        style = "Muted.TLabel" if not warning else "SubHeader.TLabel"
        for widget in self.grid_slaves(row=2, column=0) + self.grid_slaves(row=2, column=1):
            if isinstance(widget, ttk.Label):
                widget.configure(style=style)

    def _set_key_value(self, path: Path, key: str, value: str, spaced: bool = True) -> None:
        ensure_file(path)
        content = safe_read(path).splitlines()
        pattern = re.compile(rf"^\s*{re.escape(key)}\s*=")
        line = f"{key} = {value}" if spaced else f"{key}={value}"
        changed = False
        new_lines: list[str] = []
        for raw in content:
            if pattern.match(raw):
                new_lines.append(line)
                changed = True
            else:
                new_lines.append(raw)
        if not changed:
            new_lines.append(line)
        path.write_text("\n".join(new_lines).rstrip() + "\n", encoding="utf-8")

    def _get_key_value(self, path: Path, key: str) -> str:
        pattern = re.compile(rf"^\s*{re.escape(key)}\s*=\s*(.*)$")
        for raw in safe_read(path).splitlines():
            match = pattern.match(raw)
            if match:
                return match.group(1).strip()
        return ""

    def _replace_autostart_line(self, predicate: str, new_line: str) -> None:
        ensure_file(OPENBOX_AUTOSTART)
        lines = safe_read(OPENBOX_AUTOSTART).splitlines()
        changed = False
        out: list[str] = []
        for line in lines:
            if predicate in line:
                out.append(new_line)
                changed = True
            else:
                out.append(line)
        if not changed:
            out.append(new_line)
        OPENBOX_AUTOSTART.write_text("\n".join(out).rstrip() + "\n", encoding="utf-8")

    def restart_tint2(self) -> None:
        run_cmd(["pkill", "-x", "tint2"])
        subprocess.Popen(["tint2"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def reload_openbox(self) -> None:
        run_cmd(["openbox", "--reconfigure"])

    def apply_panel_height(self, height: int) -> None:
        ensure_file(TINT2_CFG)
        content = safe_read(TINT2_CFG)
        pattern = re.compile(r"^(\s*panel_size\s*=\s*\d+%\s+)\d+\s*$", re.MULTILINE)
        if pattern.search(content):
            content = pattern.sub(rf"\g<1>{height}", content, count=1)
        else:
            content = content.rstrip() + f"\npanel_size = 100% {height}\n"
        TINT2_CFG.write_text(content, encoding="utf-8")

        rc = safe_read(OPENBOX_RC)
        if rc:
            rc_new = re.sub(r"(<bottom>)\d+(</bottom>)", rf"\g<1>{height}\2", rc, count=1)
            if rc_new != rc:
                OPENBOX_RC.write_text(rc_new, encoding="utf-8")
                self.reload_openbox()

    def apply_font_profile(self, profile_name: str) -> None:
        profile = FONT_PROFILES[profile_name]
        self._set_key_value(GTK_SETTINGS, "gtk-font-name", f"DejaVu Sans {profile['gtk']}", spaced=False)
        self._set_key_value(TINT2_CFG, "font", f"DejaVu Sans {profile['panel']}", spaced=True)
        self._set_key_value(TINT2_CFG, "task_font", f"DejaVu Sans {profile['task']}", spaced=True)
        self._set_key_value(TINT2_CFG, "time1_font", f"DejaVu Sans Bold {profile['time1']}", spaced=True)
        self._set_key_value(TINT2_CFG, "time2_font", f"DejaVu Sans {profile['time2']}", spaced=True)
        self.restart_tint2()

    def get_font_profile(self) -> str:
        gtk_font = self._get_key_value(GTK_SETTINGS, "gtk-font-name")
        if gtk_font.endswith(" 9"):
            return "Compact"
        if gtk_font.endswith(" 11"):
            return "Large"
        return "Comfortable"

    def set_dark_preference(self, enabled: bool) -> None:
        self._set_key_value(GTK_SETTINGS, "gtk-application-prefer-dark-theme", "1" if enabled else "0", spaced=False)

    def get_dark_preference(self) -> bool:
        return self._get_key_value(GTK_SETTINGS, "gtk-application-prefer-dark-theme") == "1"

    def set_autohide(self, enabled: bool) -> None:
        self._set_key_value(TINT2_CFG, "autohide", "1" if enabled else "0", spaced=True)

    def get_autohide(self) -> bool:
        return self._get_key_value(TINT2_CFG, "autohide") == "1"

    def set_clock_seconds(self, enabled: bool) -> None:
        self._set_key_value(TINT2_CFG, "time1_format", "%H:%M:%S" if enabled else "%H:%M", spaced=True)

    def get_clock_seconds(self) -> bool:
        return self._get_key_value(TINT2_CFG, "time1_format") == "%H:%M:%S"

    def get_panel_height(self) -> int:
        panel_size = self._get_key_value(TINT2_CFG, "panel_size")
        match = re.search(r"\d+%\s+(\d+)", panel_size)
        if match:
            return int(match.group(1))
        return 44

    def get_nm_applet_autostart(self) -> bool:
        for line in safe_read(OPENBOX_AUTOSTART).splitlines():
            if "nm-applet --sm-disable" in line:
                return not line.lstrip().startswith("#")
        return True

    def set_nm_applet_autostart(self, enabled: bool) -> None:
        ensure_file(OPENBOX_AUTOSTART)
        lines = safe_read(OPENBOX_AUTOSTART).splitlines()
        changed = False
        out: list[str] = []
        for line in lines:
            if "nm-applet --sm-disable" in line:
                stripped = line.lstrip()
                indent = line[: len(line) - len(stripped)]
                clean = stripped[1:].lstrip() if stripped.startswith("#") else stripped
                if enabled:
                    out.append(indent + clean)
                else:
                    out.append(indent + "# " + clean)
                changed = True
            else:
                out.append(line)
        if not changed and enabled:
            out.append("(sleep 4; nm-applet --sm-disable) &")
        OPENBOX_AUTOSTART.write_text("\n".join(out).rstrip() + "\n", encoding="utf-8")

        if enabled:
            subprocess.Popen(["nm-applet", "--sm-disable"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            run_cmd(["pkill", "-x", "nm-applet"])

    def get_startup_wallpaper_mode(self) -> str:
        text = safe_read(OPENBOX_AUTOSTART)
        if "crixa-wallpaper random" in text:
            return "random"
        return "apply-current"

    def set_startup_wallpaper_mode(self, mode: str) -> None:
        text = safe_read(OPENBOX_AUTOSTART)
        if not text:
            return
        text = text.replace("crixa-wallpaper apply-current", f"crixa-wallpaper {mode}")
        text = text.replace("crixa-wallpaper random", f"crixa-wallpaper {mode}")
        OPENBOX_AUTOSTART.write_text(text, encoding="utf-8")

    def get_current_wallpaper(self) -> str:
        result = run_cmd(["crixa-wallpaper", "status"])
        if result.returncode == 0:
            return result.stdout.strip()
        return "unknown"

    def refresh_wallpaper_label(self) -> None:
        value = self.get_current_wallpaper()
        if "/" in value:
            value = value.rsplit("/", 1)[-1]
        self.wallpaper_var.set(value)

    def wallpaper_action(self, action: str) -> None:
        result = run_cmd(["crixa-wallpaper", action])
        if result.returncode == 0:
            self.refresh_wallpaper_label()
            self.set_status(f"Wallpaper: {action}")
        else:
            self.set_status("Failed to change wallpaper", warning=True)

    def open_path(self, path: str) -> None:
        subprocess.Popen(["thunar", path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def launch(self, cmd: list[str]) -> None:
        subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def xrandr_snapshot(self) -> tuple[str, list[str], str]:
        result = run_cmd(["xrandr", "--query"])
        if result.returncode != 0:
            return "", [], ""

        lines = result.stdout.splitlines()
        output_name = ""
        start_idx = -1
        first_connected: tuple[str, int] | None = None

        for idx, line in enumerate(lines):
            if " connected" in line and not line.startswith(" "):
                name = line.split()[0]
                if first_connected is None:
                    first_connected = (name, idx)
                if " primary " in f" {line} ":
                    output_name = name
                    start_idx = idx
                    break

        if not output_name and first_connected:
            output_name, start_idx = first_connected
        if not output_name:
            return "", [], ""

        modes: list[str] = []
        current_mode = ""
        for line in lines[start_idx + 1 :]:
            if line and not line.startswith(" "):
                break
            match = re.match(r"^\s+([0-9]+x[0-9]+)\s", line)
            if not match:
                continue
            mode = match.group(1)
            if mode not in modes:
                modes.append(mode)
            if "*" in line:
                current_mode = mode

        return output_name, modes, current_mode

    def refresh_display_info(self) -> None:
        output, modes, current = self.xrandr_snapshot()
        if not output:
            self.display_output_var.set("No display output detected")
            self.current_mode_var.set("n/a")
            self.mode_combo.configure(values=[])
            self.mode_var.set("")
            return

        self.display_output_var.set(output)
        self.current_mode_var.set(current or "n/a")
        self.mode_combo.configure(values=modes)
        if current:
            self.mode_var.set(current)
        elif modes:
            self.mode_var.set(modes[0])
        else:
            self.mode_var.set("")

    def apply_selected_resolution(self) -> None:
        output = self.display_output_var.get()
        mode = self.mode_var.get().strip()
        if not output or not mode or output.startswith("No display"):
            self.set_status("No display mode selected", warning=True)
            return

        result = run_cmd(["xrandr", "--output", output, "--mode", mode, "--scale", "1x1"])
        run_cmd(["xrandr", "--dpi", "96"])
        if result.returncode == 0:
            self.refresh_display_info()
            self.set_status(f"Resolution applied: {mode}")
        else:
            self.set_status("Failed to apply resolution", warning=True)

    def apply_best_resolution(self) -> None:
        output, modes, _ = self.xrandr_snapshot()
        if not output or not modes:
            self.set_status("No modes available for auto-select", warning=True)
            return

        order = VIRT_PREFERRED_MODES if is_virtualized() else PREFERRED_MODES
        target = ""
        for candidate in order:
            if candidate in modes:
                target = candidate
                break

        if not target:
            def pixels(mode: str) -> int:
                x_val, y_val = mode.split("x", 1)
                return int(x_val) * int(y_val)

            target = sorted(modes, key=pixels, reverse=True)[0]

        self.mode_var.set(target)
        self.apply_selected_resolution()

    def apply_panel_page(self) -> None:
        self.set_autohide(self.autohide_var.get())
        self.set_clock_seconds(self.clock_seconds_var.get())
        self.apply_panel_height(self.panel_height_var.get())
        self.restart_tint2()
        self.set_status("Panel settings applied")

    def apply_appearance_page(self) -> None:
        self.apply_font_profile(self.font_var.get())
        self.set_dark_preference(self.dark_var.get())
        self.set_status("Appearance settings applied")

    def apply_startup_page(self) -> None:
        self.set_nm_applet_autostart(self.nm_var.get())
        self.set_startup_wallpaper_mode(self.wall_start_mode.get())
        self.set_status("Startup settings applied")

    def _load_state(self) -> None:
        self.refresh_display_info()
        self.font_var.set(self.get_font_profile())
        self.dark_var.set(self.get_dark_preference())
        self.autohide_var.set(self.get_autohide())
        self.clock_seconds_var.set(self.get_clock_seconds())
        self.panel_height_var.set(self.get_panel_height())
        self.nm_var.set(self.get_nm_applet_autostart())
        self.wall_start_mode.set(self.get_startup_wallpaper_mode())
        self.refresh_wallpaper_label()

    def _build_display_page(self) -> ttk.Frame:
        page = ttk.Frame(self.content, style="Surface.TFrame")
        page.grid_columnconfigure(0, weight=1)

        card = ttk.LabelFrame(page, text="Display", style="Card.TLabelframe")
        card.grid(row=0, column=0, sticky="ew", padx=8, pady=(4, 10))
        card.grid_columnconfigure(1, weight=1)

        self.display_output_var = tk.StringVar(value="")
        self.current_mode_var = tk.StringVar(value="")
        self.mode_var = tk.StringVar(value="")

        ttk.Label(card, text="Output:", style="Muted.TLabel").grid(row=0, column=0, sticky="w", padx=12, pady=(10, 6))
        ttk.Label(card, textvariable=self.display_output_var).grid(row=0, column=1, sticky="w", padx=(4, 12), pady=(10, 6))

        ttk.Label(card, text="Current:", style="Muted.TLabel").grid(row=1, column=0, sticky="w", padx=12, pady=6)
        ttk.Label(card, textvariable=self.current_mode_var).grid(row=1, column=1, sticky="w", padx=(4, 12), pady=6)

        ttk.Label(card, text="Target:", style="Muted.TLabel").grid(row=2, column=0, sticky="w", padx=12, pady=6)
        self.mode_combo = ttk.Combobox(card, textvariable=self.mode_var, state="readonly", width=20)
        self.mode_combo.grid(row=2, column=1, sticky="w", padx=(4, 12), pady=6)

        row = ttk.Frame(card, style="Panel.TFrame")
        row.grid(row=3, column=0, columnspan=2, sticky="ew", padx=12, pady=(8, 12))
        ttk.Button(row, text="Refresh Modes", command=self.refresh_display_info).pack(side="left", padx=(0, 8))
        ttk.Button(row, text="Apply Selected", command=self.apply_selected_resolution).pack(side="left", padx=8)
        ttk.Button(row, text="Auto Best", command=self.apply_best_resolution).pack(side="left", padx=8)

        return page

    def _build_appearance_page(self) -> ttk.Frame:
        page = ttk.Frame(self.content, style="Surface.TFrame")
        page.grid_columnconfigure(0, weight=1)

        card = ttk.LabelFrame(page, text="Appearance", style="Card.TLabelframe")
        card.grid(row=0, column=0, sticky="ew", padx=8, pady=(4, 10))
        card.grid_columnconfigure(1, weight=1)

        self.font_var = tk.StringVar(value="Comfortable")
        self.dark_var = tk.BooleanVar(value=False)
        self.wallpaper_var = tk.StringVar(value="unknown")

        ttk.Label(card, text="Font Profile:", style="Muted.TLabel").grid(row=0, column=0, sticky="w", padx=12, pady=(10, 6))
        ttk.Combobox(card, textvariable=self.font_var, values=list(FONT_PROFILES.keys()), state="readonly", width=20).grid(
            row=0, column=1, sticky="w", padx=(4, 12), pady=(10, 6)
        )

        ttk.Checkbutton(card, text="Prefer dark app theme", variable=self.dark_var).grid(
            row=1, column=0, columnspan=2, sticky="w", padx=12, pady=6
        )

        ttk.Label(card, text="Current Wallpaper:", style="Muted.TLabel").grid(row=2, column=0, sticky="w", padx=12, pady=6)
        ttk.Label(card, textvariable=self.wallpaper_var).grid(row=2, column=1, sticky="w", padx=(4, 12), pady=6)

        wall_row = ttk.Frame(card, style="Panel.TFrame")
        wall_row.grid(row=3, column=0, columnspan=2, sticky="ew", padx=12, pady=(8, 6))
        ttk.Button(wall_row, text="Previous", command=lambda: self.wallpaper_action("prev")).pack(side="left", padx=(0, 8))
        ttk.Button(wall_row, text="Next", command=lambda: self.wallpaper_action("next")).pack(side="left", padx=8)
        ttk.Button(wall_row, text="Random", command=lambda: self.wallpaper_action("random")).pack(side="left", padx=8)
        ttk.Button(wall_row, text="Open Folder", command=lambda: self.open_path("/usr/share/backgrounds/crixa")).pack(side="left", padx=8)

        action_row = ttk.Frame(card, style="Panel.TFrame")
        action_row.grid(row=4, column=0, columnspan=2, sticky="ew", padx=12, pady=(8, 12))
        ttk.Button(action_row, text="Apply Appearance", command=self.apply_appearance_page).pack(side="left")

        return page

    def _build_panel_page(self) -> ttk.Frame:
        page = ttk.Frame(self.content, style="Surface.TFrame")
        page.grid_columnconfigure(0, weight=1)

        card = ttk.LabelFrame(page, text="Panel & Dock", style="Card.TLabelframe")
        card.grid(row=0, column=0, sticky="ew", padx=8, pady=(4, 10))
        card.grid_columnconfigure(0, weight=1)

        self.panel_height_var = tk.IntVar(value=44)
        self.autohide_var = tk.BooleanVar(value=False)
        self.clock_seconds_var = tk.BooleanVar(value=False)

        ttk.Label(card, text="Taskbar Height", style="Muted.TLabel").grid(row=0, column=0, sticky="w", padx=12, pady=(10, 4))
        scale = ttk.Scale(card, from_=36, to=56, variable=self.panel_height_var, orient="horizontal")
        scale.grid(row=1, column=0, sticky="ew", padx=12, pady=(0, 6))
        ttk.Label(card, textvariable=self.panel_height_var).grid(row=2, column=0, sticky="w", padx=12, pady=(0, 6))

        ttk.Checkbutton(card, text="Enable panel auto-hide", variable=self.autohide_var).grid(row=3, column=0, sticky="w", padx=12, pady=6)
        ttk.Checkbutton(card, text="Show seconds in clock", variable=self.clock_seconds_var).grid(row=4, column=0, sticky="w", padx=12, pady=6)

        row = ttk.Frame(card, style="Panel.TFrame")
        row.grid(row=5, column=0, sticky="ew", padx=12, pady=(8, 12))
        ttk.Button(row, text="Apply Panel Settings", command=self.apply_panel_page).pack(side="left", padx=(0, 8))
        ttk.Button(row, text="Restart Panel", command=self.restart_tint2).pack(side="left", padx=8)

        return page

    def _build_startup_page(self) -> ttk.Frame:
        page = ttk.Frame(self.content, style="Surface.TFrame")
        page.grid_columnconfigure(0, weight=1)

        card = ttk.LabelFrame(page, text="Startup", style="Card.TLabelframe")
        card.grid(row=0, column=0, sticky="ew", padx=8, pady=(4, 10))
        card.grid_columnconfigure(1, weight=1)

        self.nm_var = tk.BooleanVar(value=True)
        self.wall_start_mode = tk.StringVar(value="apply-current")

        ttk.Checkbutton(card, text="Start Network Tray (nm-applet)", variable=self.nm_var).grid(
            row=0, column=0, columnspan=2, sticky="w", padx=12, pady=(10, 8)
        )

        ttk.Label(card, text="Wallpaper On Login:", style="Muted.TLabel").grid(row=1, column=0, sticky="w", padx=12, pady=6)
        ttk.Combobox(card, textvariable=self.wall_start_mode, values=["apply-current", "random"], state="readonly", width=20).grid(
            row=1, column=1, sticky="w", padx=(4, 12), pady=6
        )

        ttk.Label(
            card,
            text="Boot splash is managed by Plymouth and does not override desktop styling.",
            style="Muted.TLabel",
        ).grid(row=2, column=0, columnspan=2, sticky="w", padx=12, pady=6)

        row = ttk.Frame(card, style="Panel.TFrame")
        row.grid(row=3, column=0, columnspan=2, sticky="ew", padx=12, pady=(8, 12))
        ttk.Button(row, text="Apply Startup Settings", command=self.apply_startup_page).pack(side="left")

        return page

    def _build_apps_page(self) -> ttk.Frame:
        page = ttk.Frame(self.content, style="Surface.TFrame")
        page.grid_columnconfigure(0, weight=1)

        card = ttk.LabelFrame(page, text="Applications", style="Card.TLabelframe")
        card.grid(row=0, column=0, sticky="ew", padx=8, pady=(4, 10))

        row1 = ttk.Frame(card, style="Panel.TFrame")
        row1.grid(row=0, column=0, sticky="ew", padx=12, pady=(10, 8))
        ttk.Button(row1, text="Browser", command=lambda: self.launch(["crixa-browser"])).pack(side="left", padx=(0, 8))
        ttk.Button(row1, text="Terminal", command=lambda: self.launch(["crixa-terminal"])).pack(side="left", padx=8)
        ttk.Button(row1, text="Files", command=lambda: self.launch(["crixa-files"])).pack(side="left", padx=8)
        ttk.Button(row1, text="Store", command=lambda: self.launch(["crixa-store"])).pack(side="left", padx=8)

        row2 = ttk.Frame(card, style="Panel.TFrame")
        row2.grid(row=1, column=0, sticky="ew", padx=12, pady=(0, 8))
        ttk.Button(row2, text="Task Manager", command=lambda: self.launch(["crixa-task-manager"])).pack(side="left", padx=(0, 8))
        ttk.Button(row2, text="YouTube", command=lambda: self.launch(["crixa-browser", "https://www.youtube.com"])).pack(side="left", padx=8)
        ttk.Button(row2, text="Wallpapers", command=lambda: self.open_path("/usr/share/backgrounds/crixa")).pack(side="left", padx=8)

        row3 = ttk.Frame(card, style="Panel.TFrame")
        row3.grid(row=2, column=0, sticky="ew", padx=12, pady=(0, 12))
        ttk.Button(row3, text="Install to Disk", command=lambda: self.launch(["crixa-installer"])).pack(side="left", padx=(0, 8))
        ttk.Button(row3, text="Updater", command=lambda: self.launch(["crixa-updater"])).pack(side="left", padx=8)

        return page

    def _build_system_page(self) -> ttk.Frame:
        page = ttk.Frame(self.content, style="Surface.TFrame")
        page.grid_columnconfigure(0, weight=1)

        card = ttk.LabelFrame(page, text="System", style="Card.TLabelframe")
        card.grid(row=0, column=0, sticky="ew", padx=8, pady=(4, 10))

        row1 = ttk.Frame(card, style="Panel.TFrame")
        row1.grid(row=0, column=0, sticky="ew", padx=12, pady=(10, 8))
        ttk.Button(row1, text="Reconfigure Openbox", command=self.reload_openbox).pack(side="left", padx=(0, 8))
        ttk.Button(row1, text="Restart Session", command=lambda: run_cmd(["openbox", "--restart"])).pack(side="left", padx=8)

        row2 = ttk.Frame(card, style="Panel.TFrame")
        row2.grid(row=1, column=0, sticky="ew", padx=12, pady=(0, 12))
        ttk.Button(row2, text="Open Config Folder", command=lambda: self.open_path(str(CONFIG_HOME))).pack(side="left")
        ttk.Button(row2, text="Wayland Track", command=lambda: self.launch(["crixa-wayland-control"])).pack(side="left", padx=8)

        return page

    def _build_about_page(self) -> ttk.Frame:
        page = ttk.Frame(self.content, style="Surface.TFrame")
        page.grid_columnconfigure(0, weight=1)

        card = ttk.LabelFrame(page, text="About CRIXA", style="Card.TLabelframe")
        card.grid(row=0, column=0, sticky="ew", padx=8, pady=(4, 10))

        details = [
            "CRIXA OS v0",
            "Window Manager: Openbox",
            "Panel: Tint2",
            f"Kernel: {platform.release()}",
            "Control Center: modular profile-based settings",
        ]
        for idx, line in enumerate(details):
            ttk.Label(card, text=line).grid(row=idx, column=0, sticky="w", padx=12, pady=6)

        return page


def main() -> int:
    app = CrixaControlCenter()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
