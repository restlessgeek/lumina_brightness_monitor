"""
tray_manager.py
System tray integration using pystray with Apple-inspired minimalist iconography
and thread-safe Tkinter coordination.
"""

import os
import math
import logging
from typing import Callable, Optional
from PIL import Image, ImageDraw
import pystray

logger = logging.getLogger(__name__)


def create_apple_sun_icon(size: int = 128, accent_color: str = "#0071e3") -> Image.Image:
    """
    Renders an Apple-inspired minimalist sun/brightness icon with anti-aliasing.
    """
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    center = size / 2.0
    core_radius = size * 0.22

    # Draw sun rays (8 rounded rays)
    num_rays = 8
    ray_inner = size * 0.32
    ray_outer = size * 0.44
    ray_width = max(2, int(size * 0.055))

    for i in range(num_rays):
        angle = (i * 2 * math.pi) / num_rays
        x1 = center + ray_inner * math.cos(angle)
        y1 = center + ray_inner * math.sin(angle)
        x2 = center + ray_outer * math.cos(angle)
        y2 = center + ray_outer * math.sin(angle)
        draw.line([(x1, y1), (x2, y2)], fill=accent_color, width=ray_width)

    # Center sun circle
    x0 = center - core_radius
    y0 = center - core_radius
    x1 = center + core_radius
    y1 = center + core_radius
    draw.ellipse([x0, y0, x1, y1], fill=accent_color)

    return img


class TrayManager:
    """Manages the background system tray icon and contextual menu."""

    def __init__(
        self,
        on_show_window: Callable[[], None],
        on_open_settings: Callable[[], None],
        on_apply_preset: Callable[[int], None],
        on_toggle_startup: Callable[[bool], None],
        on_quit_app: Callable[[], None],
        is_startup_enabled: Callable[[], bool],
    ):
        self.on_show_window = on_show_window
        self.on_open_settings = on_open_settings
        self.on_apply_preset = on_apply_preset
        self.on_toggle_startup = on_toggle_startup
        self.on_quit_app = on_quit_app
        self.is_startup_enabled = is_startup_enabled

        self.icon: Optional[pystray.Icon] = None
        self._image = create_apple_sun_icon(64, accent_color="#0071e3")

    def _build_menu(self) -> pystray.Menu:
        return pystray.Menu(
            pystray.MenuItem("☀️ Open Lumina", self._handle_show, default=True),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Brightness Presets", pystray.Menu(
                pystray.MenuItem("100%  •  Maximum", lambda: self.on_apply_preset(100)),
                pystray.MenuItem("75%  •  Daylight", lambda: self.on_apply_preset(75)),
                pystray.MenuItem("50%  •  Relax", lambda: self.on_apply_preset(50)),
                pystray.MenuItem("25%  •  Night", lambda: self.on_apply_preset(25)),
            )),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(
                "Launch at Startup",
                self._handle_toggle_startup,
                checked=lambda item: self.is_startup_enabled()
            ),
            pystray.MenuItem("⚙️ Preferences...", self._handle_open_settings),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Quit Lumina", self._handle_quit),
        )

    def _handle_show(self, icon=None, item=None):
        self.on_show_window()

    def _handle_open_settings(self, icon=None, item=None):
        self.on_open_settings()

    def _handle_toggle_startup(self, icon=None, item=None):
        current = self.is_startup_enabled()
        self.on_toggle_startup(not current)
        if self.icon:
            self.icon.update_menu()

    def _handle_quit(self, icon=None, item=None):
        self.on_quit_app()

    def start(self):
        """Starts the system tray icon detached from the main thread."""
        self.icon = pystray.Icon(
            name="LuminaBrightness",
            icon=self._image,
            title="Lumina Display Brightness",
            menu=self._build_menu(),
        )
        self.icon.run_detached()
        logger.info("System tray icon started.")

    def update_menu(self):
        if self.icon:
            self.icon.menu = self._build_menu()
            self.icon.update_menu()

    def stop(self):
        if self.icon:
            try:
                self.icon.stop()
            except Exception as e:
                logger.warning(f"Error stopping tray icon: {e}")
            self.icon = None
