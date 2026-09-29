"""
brightness_manager.py
Handles monitor discovery and asynchronous, debounced brightness adjustment
for external displays (via DDC/CI / DXVA2) and internal laptop displays (WMI).
"""

import threading
import time
import logging
from typing import List, Dict, Any, Optional, Callable
import screen_brightness_control as sbc

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


class MonitorInfo:
    def __init__(self, raw_info: Dict[str, Any], current_brightness: int):
        self.raw_info = raw_info
        self.name: str = raw_info.get("name") or "Generic Display"
        self.model: str = raw_info.get("model") or "Unknown Model"
        self.serial: str = raw_info.get("serial") or ""
        self.manufacturer: str = raw_info.get("manufacturer") or "Unknown"
        self.index: int = raw_info.get("index", 0)
        self.uid: str = raw_info.get("uid") or str(self.index)
        
        # Unique identifier used for addressing the display
        # Prefer serial number if available, else index
        if self.serial and self.serial != "None" and len(self.serial) > 2:
            self.identifier = self.serial
        else:
            self.identifier = self.index

        # Detect control method (DDC/CI VCP or Internal WMI)
        method_obj = raw_info.get("method")
        method_name = getattr(method_obj, "__name__", str(method_obj))
        if "VCP" in method_name or "DDC" in method_name:
            self.method_display = "DDC/CI (External)"
            self.is_external = True
        elif "WMI" in method_name:
            self.method_display = "Internal (WMI)"
            self.is_external = False
        else:
            self.method_display = "Hardware VCP"
            self.is_external = True

        self.brightness: int = max(0, min(100, current_brightness))
        self.is_controllable: bool = True
        self.error_message: Optional[str] = None

    def display_title(self) -> str:
        """Formatted title for display header."""
        if self.name and self.name != "Generic Display":
            return self.name
        if self.manufacturer and self.manufacturer != "Unknown":
            return f"{self.manufacturer} Display"
        return f"Display #{self.index + 1}"


class BrightnessManager:
    """
    Manages display enumeration and thread-safe, debounced brightness adjustments.
    Prevents flooding the I2C bus over DDC/CI while maintaining instant UI responsiveness.
    """

    def __init__(self):
        self.monitors: List[MonitorInfo] = []
        self._lock = threading.Lock()
        
        # Debouncing queue: target brightness per monitor identifier
        self._pending_updates: Dict[Any, int] = {}
        self._worker_event = threading.Event()
        self._stop_event = threading.Event()
        
        # Status callback: fn(status_text: str, is_error: bool)
        self.on_status_change: Optional[Callable[[str, bool], None]] = None
        
        # Monitor update callback: fn(identifier: Any, brightness: int)
        self.on_monitor_updated: Optional[Callable[[Any, int], None]] = None

        # Start background I2C worker thread
        self._worker_thread = threading.Thread(target=self._worker_loop, daemon=True, name="BrightnessWorker")
        self._worker_thread.start()

    def discover_monitors(self) -> List[MonitorInfo]:
        """
        Scans all connected monitors and queries their current brightness.
        Returns a list of MonitorInfo objects.
        """
        logger.info("Scanning for connected displays...")
        discovered: List[MonitorInfo] = []
        try:
            raw_monitors = sbc.list_monitors_info()
            logger.info(f"Found {len(raw_monitors)} raw monitor(s)")

            for idx, raw in enumerate(raw_monitors):
                # Ensure index is set
                if "index" not in raw:
                    raw["index"] = idx

                # Get current brightness for this specific monitor
                ident = raw.get("serial") or idx
                try:
                    b_val = sbc.get_brightness(display=ident)
                    if isinstance(b_val, list):
                        curr_b = b_val[0] if len(b_val) > 0 else 50
                    else:
                        curr_b = int(b_val)
                except Exception as ex:
                    logger.warning(f"Could not read brightness for monitor {idx} ({ident}): {ex}")
                    try:
                        # Fallback to display index
                        b_val = sbc.get_brightness(display=idx)
                        curr_b = b_val[0] if isinstance(b_val, list) else int(b_val)
                    except Exception:
                        curr_b = 50

                mon = MonitorInfo(raw, curr_b)
                discovered.append(mon)
                logger.info(f"Initialized monitor: {mon.display_title()} [{mon.method_display}] at {mon.brightness}%")

        except Exception as e:
            logger.error(f"Error discovering monitors: {e}")
            if self.on_status_change:
                self.on_status_change(f"Discovery error: {e}", True)

        with self._lock:
            self.monitors = discovered

        return discovered

    def set_brightness(self, identifier: Any, target_brightness: int, immediate: bool = False):
        """
        Requests brightness change for a specific monitor.
        Queues the update for the worker thread with debouncing.
        """
        target = max(0, min(100, int(target_brightness)))
        with self._lock:
            # Update local state immediately for UI consistency
            for m in self.monitors:
                if m.identifier == identifier:
                    m.brightness = target
                    break
            self._pending_updates[identifier] = target

        # Signal the worker thread
        self._worker_event.set()

    def set_all_brightness(self, target_brightness: int):
        """
        Adjusts all connected displays to the given brightness level.
        """
        target = max(0, min(100, int(target_brightness)))
        with self._lock:
            for m in self.monitors:
                m.brightness = target
                self._pending_updates[m.identifier] = target
        self._worker_event.set()

    def get_monitor_by_id(self, identifier: Any) -> Optional[MonitorInfo]:
        with self._lock:
            for m in self.monitors:
                if m.identifier == identifier:
                    return m
        return None

    def _worker_loop(self):
        """
        Background worker that drains pending updates with a debounce interval
        so external monitor I2C buses aren't overloaded during fast slider movement.
        """
        while not self._stop_event.is_set():
            # Wait until there is work or check periodically
            self._worker_event.wait(timeout=0.1)
            self._worker_event.clear()

            # Small debounce delay: allow rapid slider events to settle
            time.sleep(0.04)

            # Grab current snapshot of pending requests
            with self._lock:
                work_items = dict(self._pending_updates)
                self._pending_updates.clear()

            if not work_items:
                continue

            for identifier, level in work_items.items():
                if self._stop_event.is_set():
                    break
                
                try:
                    logger.debug(f"Applying brightness {level}% to display {identifier}...")
                    sbc.set_brightness(level, display=identifier)
                    
                    if self.on_monitor_updated:
                        self.on_monitor_updated(identifier, level)

                except Exception as err:
                    logger.warning(f"Failed to set brightness for display {identifier}: {err}")
                    # Try falling back by index if identifier was serial
                    fallback_success = False
                    with self._lock:
                        mon = self.get_monitor_by_id(identifier)
                        if mon and mon.index is not None and mon.index != identifier:
                            try:
                                sbc.set_brightness(level, display=mon.index)
                                fallback_success = True
                            except Exception:
                                pass

                    if not fallback_success and self.on_status_change:
                        msg = f"Hardware note: monitor {identifier} did not accept command. Ensure DDC/CI is enabled in monitor OSD."
                        self.on_status_change(msg, True)

                # Hardware breathing room between successive I2C display commands
                time.sleep(0.03)

    def shutdown(self):
        """Gracefully halts the background thread."""
        self._stop_event.set()
        self._worker_event.set()
        if self._worker_thread.is_alive():
            self._worker_thread.join(timeout=1.0)
