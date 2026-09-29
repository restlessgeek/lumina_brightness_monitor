"""
app.py
Lumina Display Brightness Controller
An Apple-inspired desktop app for adjusting external (DDC/CI) and internal display brightness on Windows.
"""

import os
import sys
import threading
import tkinter as tk
from tkinter import messagebox
from typing import Dict, Any, Optional
import customtkinter as ctk
from PIL import Image

from brightness_manager import BrightnessManager, MonitorInfo
from config_manager import ConfigManager
from tray_manager import TrayManager, create_apple_sun_icon

# Base styling inspired by macOS Sonoma / Sequoia
FONT_FAMILY = "Segoe UI"  # Clean sans-serif on Windows matching SF Pro proportions
COLOR_ACCENT = "#0071e3"  # Apple Blue
COLOR_ACCENT_HOVER = "#0077ed"

# Configure CustomTkinter
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")


class SegmentedPresets(ctk.CTkFrame):
    """macOS-style segmented pill control for brightness presets."""

    def __init__(self, master, on_select, presets=None, **kwargs):
        super().__init__(
            master,
            corner_radius=10,
            fg_color=("gray85", "#202022"),
            border_width=1,
            border_color=("gray75", "#323235"),
            **kwargs,
        )
        self.on_select = on_select
        self.presets = presets or [25, 50, 75, 100]
        self.buttons = []

        self._build_segments()

    def _build_segments(self):
        for idx, val in enumerate(self.presets):
            btn = ctk.CTkButton(
                self,
                text=f"{val}%",
                width=52,
                height=26,
                corner_radius=8,
                fg_color="transparent",
                hover_color=("gray75", "#2e2e32"),
                text_color=("gray20", "#e5e5ea"),
                font=ctk.CTkFont(family=FONT_FAMILY, size=11, weight="bold"),
                command=lambda v=val: self.on_select(v),
            )
            btn.pack(side="left", padx=2, pady=2, expand=True, fill="x")
            self.buttons.append(btn)


class AppleDisplayCard(ctk.CTkFrame):
    """
    macOS Control Center-inspired Display Slider Card.
    Features rounded container, hardware badges, bold readout, and smooth pill slider.
    """

    def __init__(self, master, monitor: MonitorInfo, on_brightness_change, **kwargs):
        super().__init__(
            master,
            corner_radius=16,
            fg_color=("#ffffff", "#28282a"),
            border_width=1,
            border_color=("#e5e5ea", "#38383a"),
            **kwargs,
        )
        self.monitor = monitor
        self.on_brightness_change = on_brightness_change
        self._is_updating = False

        self._build_ui()

    def _build_ui(self):
        # 1. Header Row: Icon, Monitor Name, Badges, Percentage
        header_row = ctk.CTkFrame(self, fg_color="transparent")
        header_row.pack(fill="x", padx=18, pady=(16, 8))

        # Title & Subtitle Left
        left_box = ctk.CTkFrame(header_row, fg_color="transparent")
        left_box.pack(side="left", fill="x", expand=True)

        name_row = ctk.CTkFrame(left_box, fg_color="transparent")
        name_row.pack(anchor="w")

        icon_glyph = "🖥️" if self.monitor.is_external else "💻"
        icon_lbl = ctk.CTkLabel(
            name_row,
            text=icon_glyph,
            font=ctk.CTkFont(size=16),
        )
        icon_lbl.pack(side="left", padx=(0, 6))

        title_lbl = ctk.CTkLabel(
            name_row,
            text=self.monitor.display_title(),
            font=ctk.CTkFont(family=FONT_FAMILY, size=15, weight="bold"),
            text_color=("gray10", "#f5f5f7"),
            anchor="w",
        )
        title_lbl.pack(side="left")

        # Pill badge for connection method (Apple-style subtle tag)
        method_badge_color = ("#e5f1ff", "#182d49") if self.monitor.is_external else ("#e8f8ed", "#1b3824")
        method_text_color = ("#0071e3", "#60a5fa") if self.monitor.is_external else ("#1b873f", "#4ade80")
        method_badge = ctk.CTkLabel(
            name_row,
            text=f" {self.monitor.method_display} ",
            font=ctk.CTkFont(family=FONT_FAMILY, size=10, weight="bold"),
            fg_color=method_badge_color,
            text_color=method_text_color,
            corner_radius=6,
            height=20,
        )
        method_badge.pack(side="left", padx=8)

        # Percentage readout on the right
        self.pct_label = ctk.CTkLabel(
            header_row,
            text=f"{self.monitor.brightness}%",
            font=ctk.CTkFont(family=FONT_FAMILY, size=18, weight="bold"),
            text_color=(COLOR_ACCENT, "#60a5fa"),
            width=54,
            anchor="e",
        )
        self.pct_label.pack(side="right")

        # 2. macOS Control Center-style Slider Row (with sun icons on flanks)
        slider_container = ctk.CTkFrame(self, fg_color="transparent")
        slider_container.pack(fill="x", padx=18, pady=(4, 10))

        # Soft sun (dim)
        dim_sun = ctk.CTkLabel(
            slider_container,
            text="🔅",
            font=ctk.CTkFont(size=14),
            text_color=("gray50", "gray50"),
        )
        dim_sun.pack(side="left", padx=(0, 10))

        # macOS Pill Slider
        self.slider = ctk.CTkSlider(
            slider_container,
            from_=0,
            to=100,
            number_of_steps=100,
            command=self._on_slider_change,
            height=22,
            progress_color=(COLOR_ACCENT, COLOR_ACCENT),
            button_color=("#ffffff", "#f5f5f7"),
            button_hover_color=("#e5e5ea", "#ffffff"),
            button_corner_radius=11,
            button_length=16,
            fg_color=("gray80", "#3a3a3c"),
        )
        self.slider.set(self.monitor.brightness)
        self.slider.pack(side="left", fill="x", expand=True)

        # Bright sun (max)
        bright_sun = ctk.CTkLabel(
            slider_container,
            text="☀️",
            font=ctk.CTkFont(size=15),
            text_color=("gray50", "gray50"),
        )
        bright_sun.pack(side="left", padx=(10, 0))

        # 3. Bottom Row: Quick Presets & Hardware Info
        bottom_row = ctk.CTkFrame(self, fg_color="transparent")
        bottom_row.pack(fill="x", padx=18, pady=(0, 14))

        # Info subtitle
        details = []
        if self.monitor.model and self.monitor.model != "Unknown Model":
            details.append(self.monitor.model)
        if self.monitor.serial:
            details.append(f"S/N: {self.monitor.serial}")
        meta_str = " • ".join(details) if details else f"Display #{self.monitor.index + 1}"

        meta_lbl = ctk.CTkLabel(
            bottom_row,
            text=meta_str,
            font=ctk.CTkFont(family=FONT_FAMILY, size=11),
            text_color=("gray50", "gray55"),
            anchor="w",
        )
        meta_lbl.pack(side="left", anchor="c")

        # Apple-style Segmented Presets
        presets_widget = SegmentedPresets(
            bottom_row,
            on_select=self.set_value,
            presets=[25, 50, 75, 100],
        )
        presets_widget.pack(side="right")

    def _on_slider_change(self, value):
        if self._is_updating:
            return
        val_int = int(round(value))
        self.pct_label.configure(text=f"{val_int}%")
        self.on_brightness_change(self.monitor.identifier, val_int)

    def set_value(self, val: int):
        val = max(0, min(100, int(val)))
        self._is_updating = True
        try:
            self.slider.set(val)
            self.pct_label.configure(text=f"{val}%")
        finally:
            self._is_updating = False
        self.on_brightness_change(self.monitor.identifier, val)

    def update_brightness_display(self, val: int):
        self._is_updating = True
        try:
            self.slider.set(val)
            self.pct_label.configure(text=f"{val}%")
        finally:
            self._is_updating = False


class LuminaApp(ctk.CTk):
    """
    Main Lumina Application Window.
    Implements Apple-inspired layout, segmented views (Displays / Preferences),
    System Tray integration, and Windows Startup control.
    """

    def __init__(self, start_minimized: bool = False):
        super().__init__()

        # Configuration and Managers
        self.config = ConfigManager()
        self.manager = BrightnessManager()
        self.manager.on_status_change = self._on_manager_status
        self.manager.on_monitor_updated = self._on_manager_monitor_updated

        # High-DPI Windows awareness
        try:
            from ctypes import windll
            windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass

        # Window Appearance & Geometry
        self.title("Lumina")
        self.geometry("540x670")
        self.minsize(500, 560)
        self.configure(fg_color=("#f5f5f7", "#1e1e1e"))

        # Set Window Icon
        self._set_app_icon()

        # Appearance mode sync
        saved_mode = self.config.get("appearance_mode", "Dark")
        ctk.set_appearance_mode(saved_mode)

        self.display_cards: Dict[Any, AppleDisplayCard] = {}
        self._is_scanning = False
        self.current_view = "displays"  # "displays" or "settings"

        # Initialize System Tray
        self.tray = TrayManager(
            on_show_window=self._show_window_from_tray,
            on_open_settings=self._open_settings_from_tray,
            on_apply_preset=self._apply_master_brightness_safe,
            on_toggle_startup=self._toggle_startup_from_tray,
            on_quit_app=self._quit_application,
            is_startup_enabled=self.config.is_registry_startup_enabled,
        )
        self.tray.start()

        # Build UI Elements
        self._build_top_toolbar()
        self._build_content_views()
        self._build_footer()

        # Intercept Close button ("X")
        self.protocol("WM_DELETE_WINDOW", self._on_window_close)

        # Keyboard shortcuts
        self.bind("<Control-r>", lambda e: self.rescan_displays())
        self.bind("<F5>", lambda e: self.rescan_displays())

        # Start minimized or show
        if start_minimized or (self.config.get("start_minimized") and "--minimized" in sys.argv):
            self.withdraw()
        else:
            self.deiconify()

        # Run initial display scan
        self.rescan_displays()

    def _set_app_icon(self):
        assets_dir = os.path.join(os.path.dirname(__file__), "assets")
        ico_path = os.path.join(assets_dir, "icon.ico")
        if os.path.exists(ico_path):
            try:
                self.iconbitmap(ico_path)
            except Exception:
                pass

    # --- UI Layout Builders ---

    def _build_top_toolbar(self):
        """macOS-style top navigation bar with segmented tab switcher."""
        self.toolbar = ctk.CTkFrame(self, fg_color="transparent")
        self.toolbar.pack(fill="x", padx=22, pady=(18, 12))

        # Left: App Brand & Icon
        brand_box = ctk.CTkFrame(self.toolbar, fg_color="transparent")
        brand_box.pack(side="left")

        app_logo = ctk.CTkLabel(
            brand_box,
            text="☀️",
            font=ctk.CTkFont(size=20),
        )
        app_logo.pack(side="left", padx=(0, 8))

        title_lbl = ctk.CTkLabel(
            brand_box,
            text="Lumina",
            font=ctk.CTkFont(family=FONT_FAMILY, size=18, weight="bold"),
            text_color=("gray10", "#f5f5f7"),
        )
        title_lbl.pack(side="left")

        # Right: macOS-style Segmented View Switcher
        nav_box = ctk.CTkFrame(
            self.toolbar,
            corner_radius=10,
            fg_color=("gray85", "#28282a"),
            border_width=1,
            border_color=("gray75", "#38383a"),
        )
        nav_box.pack(side="right")

        self.btn_nav_displays = ctk.CTkButton(
            nav_box,
            text="🖥️ Displays",
            width=88,
            height=28,
            corner_radius=8,
            fg_color=(COLOR_ACCENT, COLOR_ACCENT),
            hover_color=(COLOR_ACCENT_HOVER, COLOR_ACCENT_HOVER),
            text_color="#ffffff",
            font=ctk.CTkFont(family=FONT_FAMILY, size=12, weight="bold"),
            command=lambda: self._switch_view("displays"),
        )
        self.btn_nav_displays.pack(side="left", padx=2, pady=2)

        self.btn_nav_settings = ctk.CTkButton(
            nav_box,
            text="⚙️ Preferences",
            width=98,
            height=28,
            corner_radius=8,
            fg_color="transparent",
            hover_color=("gray75", "#353538"),
            text_color=("gray30", "#c7c7cc"),
            font=ctk.CTkFont(family=FONT_FAMILY, size=12, weight="bold"),
            command=lambda: self._switch_view("settings"),
        )
        self.btn_nav_settings.pack(side="left", padx=2, pady=2)

    def _build_content_views(self):
        """Builds both the Displays view and the Preferences view."""
        self.content_container = ctk.CTkFrame(self, fg_color="transparent")
        self.content_container.pack(fill="both", expand=True, padx=22, pady=0)

        # 1. Displays View
        self.displays_view = ctk.CTkFrame(self.content_container, fg_color="transparent")
        self._build_master_card(self.displays_view)

        # Scrollable Display Cards Frame
        self.scroll_frame = ctk.CTkScrollableFrame(
            self.displays_view,
            fg_color="transparent",
            corner_radius=0,
            label_text="Active Displays",
            label_font=ctk.CTkFont(family=FONT_FAMILY, size=13, weight="bold"),
            label_text_color=("gray40", "#8e8e93"),
        )
        self.scroll_frame.pack(fill="both", expand=True, pady=(6, 0))

        # 2. Preferences / Settings View
        self.settings_view = ctk.CTkFrame(self.content_container, fg_color="transparent")
        self._build_settings_content(self.settings_view)

        # Start on Displays view
        self.displays_view.pack(fill="both", expand=True)

    def _build_master_card(self, parent):
        """macOS Control Center-style Master Brightness Control."""
        self.master_card = ctk.CTkFrame(
            parent,
            corner_radius=16,
            fg_color=("#ffffff", "#28282a"),
            border_width=1,
            border_color=("#e5e5ea", "#38383a"),
        )
        self.master_card.pack(fill="x", pady=(0, 10))

        top_row = ctk.CTkFrame(self.master_card, fg_color="transparent")
        top_row.pack(fill="x", padx=18, pady=(14, 6))

        lbl = ctk.CTkLabel(
            top_row,
            text="⚡ Master Control (All Displays)",
            font=ctk.CTkFont(family=FONT_FAMILY, size=14, weight="bold"),
            text_color=("gray10", "#f5f5f7"),
        )
        lbl.pack(side="left")

        self.master_pct_label = ctk.CTkLabel(
            top_row,
            text="100%",
            font=ctk.CTkFont(family=FONT_FAMILY, size=15, weight="bold"),
            text_color=(COLOR_ACCENT, "#60a5fa"),
        )
        self.master_pct_label.pack(side="right")

        # Master Slider with glyphs
        slider_row = ctk.CTkFrame(self.master_card, fg_color="transparent")
        slider_row.pack(fill="x", padx=18, pady=(2, 10))

        dim_sun = ctk.CTkLabel(slider_row, text="🔅", font=ctk.CTkFont(size=14), text_color=("gray50", "gray50"))
        dim_sun.pack(side="left", padx=(0, 10))

        self.master_slider = ctk.CTkSlider(
            slider_row,
            from_=0,
            to=100,
            number_of_steps=100,
            height=22,
            command=self._on_master_slider_moved,
            progress_color=(COLOR_ACCENT, COLOR_ACCENT),
            button_color=("#ffffff", "#f5f5f7"),
            button_hover_color=("#e5e5ea", "#ffffff"),
            button_corner_radius=11,
            button_length=16,
            fg_color=("gray80", "#3a3a3c"),
        )
        self.master_slider.set(100)
        self.master_slider.pack(side="left", fill="x", expand=True)

        bright_sun = ctk.CTkLabel(slider_row, text="☀️", font=ctk.CTkFont(size=15), text_color=("gray50", "gray50"))
        bright_sun.pack(side="left", padx=(10, 0))

        # Global Quick Scenes
        scenes_row = ctk.CTkFrame(self.master_card, fg_color="transparent")
        scenes_row.pack(fill="x", padx=18, pady=(0, 14))

        scenes = [
            ("🌙 Night", 25),
            ("☕ Relax", 50),
            ("💼 Day", 75),
            ("☀️ Max", 100),
        ]
        for name, val in scenes:
            btn = ctk.CTkButton(
                scenes_row,
                text=f"{name} ({val}%)",
                height=28,
                corner_radius=8,
                fg_color=("gray90", "#202022"),
                hover_color=("gray80", "#303034"),
                text_color=("gray20", "#e5e5ea"),
                font=ctk.CTkFont(family=FONT_FAMILY, size=11, weight="bold"),
                command=lambda v=val: self._apply_master_brightness(v),
            )
            btn.pack(side="left", padx=3, expand=True, fill="x")

    def _build_settings_content(self, parent):
        """Apple System Settings-inspired Grouped Preferences List."""
        scroll_settings = ctk.CTkScrollableFrame(parent, fg_color="transparent", corner_radius=0)
        scroll_settings.pack(fill="both", expand=True)

        # Group 1: General & Startup
        self._build_settings_group_header(scroll_settings, "General & Behavior")

        group1 = ctk.CTkFrame(
            scroll_settings,
            corner_radius=14,
            fg_color=("#ffffff", "#28282a"),
            border_width=1,
            border_color=("#e5e5ea", "#38383a"),
        )
        group1.pack(fill="x", pady=(4, 16))

        # Row: Launch on Startup
        self.switch_startup = self._build_settings_switch_row(
            group1,
            title="Launch at Login",
            subtitle="Start Lumina automatically when you log into Windows",
            default_val=self.config.is_registry_startup_enabled(),
            on_change=self._on_startup_switch_toggled,
            is_first=True,
        )

        # Row: Close to Tray
        self.switch_close_tray = self._build_settings_switch_row(
            group1,
            title="Keep Running in System Tray",
            subtitle="Closing window minimizes Lumina to the taskbar tray",
            default_val=self.config.get("close_to_tray", True),
            on_change=lambda v: self.config.set("close_to_tray", v),
        )

        # Row: Start Minimized
        self.switch_start_min = self._build_settings_switch_row(
            group1,
            title="Start Silently in Tray",
            subtitle="Don't open the main window on login",
            default_val=self.config.get("start_minimized", False),
            on_change=lambda v: self.config.set("start_minimized", v),
        )

        # Group 2: Appearance
        self._build_settings_group_header(scroll_settings, "Appearance")

        group2 = ctk.CTkFrame(
            scroll_settings,
            corner_radius=14,
            fg_color=("#ffffff", "#28282a"),
            border_width=1,
            border_color=("#e5e5ea", "#38383a"),
        )
        group2.pack(fill="x", pady=(4, 16))

        theme_row = ctk.CTkFrame(group2, fg_color="transparent")
        theme_row.pack(fill="x", padx=16, pady=12)

        theme_lbl_box = ctk.CTkFrame(theme_row, fg_color="transparent")
        theme_lbl_box.pack(side="left", fill="x", expand=True)

        ctk.CTkLabel(
            theme_lbl_box,
            text="Interface Theme",
            font=ctk.CTkFont(family=FONT_FAMILY, size=13, weight="bold"),
            text_color=("gray10", "#f5f5f7"),
            anchor="w",
        ).pack(anchor="w")

        ctk.CTkLabel(
            theme_lbl_box,
            text="Select Dark, Light, or follow Windows system settings",
            font=ctk.CTkFont(family=FONT_FAMILY, size=11),
            text_color=("gray45", "#8e8e93"),
            anchor="w",
        ).pack(anchor="w")

        self.theme_segment = ctk.CTkSegmentedButton(
            theme_row,
            values=["Dark", "Light", "System"],
            command=self._change_theme,
            font=ctk.CTkFont(family=FONT_FAMILY, size=11, weight="bold"),
            corner_radius=8,
            selected_color=COLOR_ACCENT,
            selected_hover_color=COLOR_ACCENT_HOVER,
        )
        self.theme_segment.set(self.config.get("appearance_mode", "Dark"))
        self.theme_segment.pack(side="right")

        # Group 3: Hardware & DDC/CI Information
        self._build_settings_group_header(scroll_settings, "Hardware & DDC/CI Protocol")

        group3 = ctk.CTkFrame(
            scroll_settings,
            corner_radius=14,
            fg_color=("#ffffff", "#28282a"),
            border_width=1,
            border_color=("#e5e5ea", "#38383a"),
        )
        group3.pack(fill="x", pady=(4, 16))

        help_text = (
            "• External Monitors: Brightness commands are sent over your HDMI/DisplayPort cable "
            "using the VESA DDC/CI protocol.\n\n"
            "• If brightness doesn't respond: Open your monitor's physical hardware menu (using its "
            "buttons or joystick) -> Settings -> DDC/CI -> Turn ON.\n\n"
            "• Adapters: Ensure your cable or USB-C hub supports bidirectional DDC/CI data lines."
        )
        help_box = ctk.CTkLabel(
            group3,
            text=help_text,
            font=ctk.CTkFont(family=FONT_FAMILY, size=11),
            text_color=("gray40", "#98989d"),
            justify="left",
            wraplength=460,
        )
        help_box.pack(padx=16, pady=14, anchor="w")

        # App Info / Quit button
        quit_row = ctk.CTkFrame(scroll_settings, fg_color="transparent")
        quit_row.pack(fill="x", pady=(4, 20))

        ctk.CTkLabel(
            quit_row,
            text="Lumina v1.2 • Designed with Cupertino Aesthetics",
            font=ctk.CTkFont(family=FONT_FAMILY, size=11),
            text_color=("gray50", "gray50"),
        ).pack(side="left")

        ctk.CTkButton(
            quit_row,
            text="Quit Lumina",
            width=90,
            height=28,
            corner_radius=6,
            fg_color=("#fee2e2", "#3b1717"),
            hover_color=("#fecaca", "#4c1d1d"),
            text_color=("#dc2626", "#f87171"),
            font=ctk.CTkFont(family=FONT_FAMILY, size=11, weight="bold"),
            command=self._quit_application,
        ).pack(side="right")

    def _build_settings_group_header(self, parent, title: str):
        lbl = ctk.CTkLabel(
            parent,
            text=title.upper(),
            font=ctk.CTkFont(family=FONT_FAMILY, size=11, weight="bold"),
            text_color=("gray50", "#8e8e93"),
            anchor="w",
        )
        lbl.pack(fill="x", padx=6, pady=(10, 2))

    def _build_settings_switch_row(self, parent, title: str, subtitle: str, default_val: bool, on_change, is_first: bool = False):
        if not is_first:
            sep = ctk.CTkFrame(parent, height=1, fg_color=("#f0f0f2", "#353538"))
            sep.pack(fill="x", padx=16)

        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", padx=16, pady=12)

        lbl_box = ctk.CTkFrame(row, fg_color="transparent")
        lbl_box.pack(side="left", fill="x", expand=True)

        ctk.CTkLabel(
            lbl_box,
            text=title,
            font=ctk.CTkFont(family=FONT_FAMILY, size=13, weight="bold"),
            text_color=("gray10", "#f5f5f7"),
            anchor="w",
        ).pack(anchor="w")

        ctk.CTkLabel(
            lbl_box,
            text=subtitle,
            font=ctk.CTkFont(family=FONT_FAMILY, size=11),
            text_color=("gray45", "#8e8e93"),
            anchor="w",
        ).pack(anchor="w")

        switch = ctk.CTkSwitch(
            row,
            text="",
            width=46,
            progress_color=COLOR_ACCENT,
            command=lambda: on_change(bool(switch.get())),
        )
        if default_val:
            switch.select()
        else:
            switch.deselect()
        switch.pack(side="right")
        return switch

    def _build_footer(self):
        """Subtle footer status bar."""
        footer = ctk.CTkFrame(self, height=32, corner_radius=0, fg_color=("gray92", "#18181a"))
        footer.pack(fill="x", side="bottom")

        self.status_label = ctk.CTkLabel(
            footer,
            text="Ready",
            font=ctk.CTkFont(family=FONT_FAMILY, size=11),
            text_color=("gray40", "#8e8e93"),
            anchor="w",
        )
        self.status_label.pack(side="left", padx=18, pady=4)

        btn_rescan = ctk.CTkButton(
            footer,
            text="🔄 Rescan Displays",
            width=110,
            height=22,
            corner_radius=6,
            fg_color="transparent",
            hover_color=("gray85", "#28282a"),
            text_color=(COLOR_ACCENT, "#60a5fa"),
            font=ctk.CTkFont(family=FONT_FAMILY, size=11, weight="bold"),
            command=self.rescan_displays,
        )
        btn_rescan.pack(side="right", padx=14, pady=4)

    # --- View Switching ---

    def _switch_view(self, view_name: str):
        self.current_view = view_name
        if view_name == "displays":
            self.settings_view.pack_forget()
            self.displays_view.pack(fill="both", expand=True)
            self.btn_nav_displays.configure(
                fg_color=(COLOR_ACCENT, COLOR_ACCENT),
                text_color="#ffffff",
            )
            self.btn_nav_settings.configure(
                fg_color="transparent",
                text_color=("gray30", "#c7c7cc"),
            )
        else:
            self.displays_view.pack_forget()
            self.settings_view.pack(fill="both", expand=True)
            self.btn_nav_settings.configure(
                fg_color=(COLOR_ACCENT, COLOR_ACCENT),
                text_color="#ffffff",
            )
            self.btn_nav_displays.configure(
                fg_color="transparent",
                text_color=("gray30", "#c7c7cc"),
            )

    # --- Event Handlers & Control ---

    def _on_startup_switch_toggled(self, enabled: bool):
        success = self.config.set_startup(enabled)
        if not success:
            messagebox.showerror(
                "Startup Error",
                "Could not register Lumina into Windows Startup. Please verify user permissions."
            )
            if self.switch_startup:
                if enabled:
                    self.switch_startup.deselect()
                else:
                    self.switch_startup.select()
        else:
            self.tray.update_menu()
            status = "enabled" if enabled else "disabled"
            self.status_label.configure(text=f"Launch at Login {status}.")

    def _change_theme(self, choice: str):
        ctk.set_appearance_mode(choice)
        self.config.set("appearance_mode", choice)

    def rescan_displays(self):
        if self._is_scanning:
            return
        self._is_scanning = True
        self.status_label.configure(text="Scanning display hardware...")

        def _scan():
            monitors = self.manager.discover_monitors()
            self.after(0, lambda: self._on_scan_completed(monitors))

        threading.Thread(target=_scan, daemon=True).start()

    def _on_scan_completed(self, monitors):
        self._is_scanning = False
        for widget in self.scroll_frame.winfo_children():
            widget.destroy()
        self.display_cards.clear()

        if not monitors:
            empty_box = ctk.CTkFrame(
                self.scroll_frame,
                corner_radius=14,
                fg_color=("#ffffff", "#28282a"),
                border_width=1,
                border_color=("#e5e5ea", "#38383a"),
            )
            empty_box.pack(fill="x", pady=20, padx=4)

            ctk.CTkLabel(
                empty_box,
                text="No compatible displays found.",
                font=ctk.CTkFont(family=FONT_FAMILY, size=14, weight="bold"),
                text_color=("gray20", "#f5f5f7"),
            ).pack(pady=(20, 6))

            ctk.CTkLabel(
                empty_box,
                text="Please verify that DDC/CI is enabled in your monitor's OSD hardware menu.\nClick 'Preferences' to read the troubleshooting guide.",
                font=ctk.CTkFont(family=FONT_FAMILY, size=11),
                text_color=("gray50", "#8e8e93"),
                justify="center",
            ).pack(pady=(0, 20))

            self.status_label.configure(text="No monitors detected.")
            self.master_pct_label.configure(text="--%")
            return

        avg = 0
        for mon in monitors:
            card = AppleDisplayCard(
                self.scroll_frame,
                monitor=mon,
                on_brightness_change=self._on_display_brightness_changed,
            )
            card.pack(fill="x", pady=6)
            self.display_cards[mon.identifier] = card
            avg += mon.brightness

        avg = int(round(avg / len(monitors)))
        self.master_slider.set(avg)
        self.master_pct_label.configure(text=f"{avg}%")
        self.status_label.configure(
            text=f"{len(monitors)} display{'s' if len(monitors) > 1 else ''} connected • Ready"
        )

    def _on_display_brightness_changed(self, identifier, val: int):
        self.manager.set_brightness(identifier, val)
        self.status_label.configure(text=f"Adjusting brightness to {val}%...")

    def _on_master_slider_moved(self, value):
        val_int = int(round(value))
        self.master_pct_label.configure(text=f"{val_int}%")
        self._apply_master_brightness(val_int)

    def _apply_master_brightness(self, value: int):
        self.master_slider.set(value)
        self.master_pct_label.configure(text=f"{value}%")
        self.manager.set_all_brightness(value)
        for card in self.display_cards.values():
            card.update_brightness_display(value)
        self.status_label.configure(text=f"All displays set to {value}%.")

    def _apply_master_brightness_safe(self, value: int):
        self.after(0, lambda: self._apply_master_brightness(value))

    def _on_manager_status(self, status_text: str, is_error: bool):
        def _update():
            prefix = "⚠️ " if is_error else ""
            self.status_label.configure(text=f"{prefix}{status_text}")
        self.after(0, _update)

    def _on_manager_monitor_updated(self, identifier, brightness: int):
        self.after(0, lambda: self.status_label.configure(text="Ready"))

    # --- Window & Tray Lifecycle ---

    def _show_window_from_tray(self):
        self.after(0, self._restore_window)

    def _open_settings_from_tray(self):
        def _show_settings():
            self._restore_window()
            self._switch_view("settings")
        self.after(0, _show_settings)

    def _toggle_startup_from_tray(self, enable: bool):
        def _toggle():
            self.config.set_startup(enable)
            if hasattr(self, "switch_startup"):
                if enable:
                    self.switch_startup.select()
                else:
                    self.switch_startup.deselect()
            self.tray.update_menu()
        self.after(0, _toggle)

    def _restore_window(self):
        self.deiconify()
        self.lift()
        self.focus_force()

    def _on_window_close(self):
        """Handles user clicking the 'X' button."""
        if self.config.get("close_to_tray", True):
            self.withdraw()
        else:
            self._quit_application()

    def _quit_application(self):
        self.after(0, self._actual_quit)

    def _actual_quit(self):
        try:
            self.tray.stop()
        except Exception:
            pass
        self.manager.shutdown()
        self.destroy()


def main():
    start_min = "--minimized" in sys.argv
    app = LuminaApp(start_minimized=start_min)
    app.mainloop()


if __name__ == "__main__":
    main()
