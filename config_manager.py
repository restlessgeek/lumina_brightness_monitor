"""
config_manager.py
Manages user preferences and Windows Startup registry integration for Lumina.
"""

import os
import sys
import json
import winreg
import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)

CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "settings.json")
REG_KEY_PATH = r"Software\Microsoft\Windows\CurrentVersion\Run"
APP_REG_NAME = "LuminaBrightness"

DEFAULT_SETTINGS: Dict[str, Any] = {
    "launch_on_startup": False,
    "start_minimized": False,
    "close_to_tray": True,
    "appearance_mode": "Dark",
    "accent_color": "blue",
}


class ConfigManager:
    def __init__(self):
        self.settings: Dict[str, Any] = dict(DEFAULT_SETTINGS)
        self.load_settings()

    def load_settings(self):
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.settings.update(data)
            except Exception as e:
                logger.warning(f"Failed to load settings.json: {e}")
        
        # Check actual Windows Registry state to keep in sync
        reg_enabled = self.is_registry_startup_enabled()
        self.settings["launch_on_startup"] = reg_enabled

    def save_settings(self):
        try:
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(self.settings, f, indent=2)
        except Exception as e:
            logger.warning(f"Failed to save settings.json: {e}")

    def get(self, key: str, default: Any = None) -> Any:
        return self.settings.get(key, default)

    def set(self, key: str, value: Any):
        self.settings[key] = value
        self.save_settings()

    # --- Windows Registry Startup Management ---

    def _get_startup_command(self) -> str:
        """Determines the correct command to launch Lumina automatically."""
        if getattr(sys, "frozen", False):
            # Built executable (PyInstaller)
            exe_path = os.path.abspath(sys.executable)
            return f'"{exe_path}" --minimized'
        else:
            # Python script execution
            # Prefer pythonw.exe to prevent terminal window popup
            python_exe = sys.executable
            pythonw_exe = os.path.join(os.path.dirname(python_exe), "pythonw.exe")
            if not os.path.exists(pythonw_exe):
                pythonw_exe = python_exe
            
            script_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "app.py"))
            return f'"{pythonw_exe}" "{script_path}" --minimized'

    def is_registry_startup_enabled(self) -> bool:
        """Checks if Lumina is registered in HKCU Run key."""
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_KEY_PATH, 0, winreg.KEY_READ) as key:
                val, _ = winreg.QueryValueEx(key, APP_REG_NAME)
                return bool(val)
        except FileNotFoundError:
            return False
        except Exception as e:
            logger.warning(f"Error checking startup registry: {e}")
            return False

    def set_startup(self, enable: bool) -> bool:
        """Adds or removes the startup command in Windows Registry."""
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_KEY_PATH, 0, winreg.KEY_SET_VALUE) as key:
                if enable:
                    cmd = self._get_startup_command()
                    winreg.SetValueEx(key, APP_REG_NAME, 0, winreg.REG_SZ, cmd)
                    logger.info(f"Registered startup command: {cmd}")
                else:
                    try:
                        winreg.DeleteValue(key, APP_REG_NAME)
                        logger.info("Removed startup command from registry.")
                    except FileNotFoundError:
                        pass
            
            self.settings["launch_on_startup"] = enable
            self.save_settings()
            return True
        except Exception as e:
            logger.error(f"Failed to update startup registry: {e}")
            return False
