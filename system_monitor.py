"""
JARVIS System Monitor
Background QThread — polls hardware every 1.5s, emits stats_ready signal.

Device data (WiFi SSID, USB, Bluetooth) is fetched every 8s in a separate
daemon thread to avoid blocking the fast poll cycle.

Never touches UI. All results emitted via signals.
"""

import time
import logging
import subprocess
import platform
import threading
import re
from typing import Optional, List
from PyQt6.QtCore import QThread, pyqtSignal

logger = logging.getLogger("jarvis.sysmon")
_SYSTEM = platform.system()


# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║  DEVICE DETECTION HELPERS (module-level, no Qt)                            ║
# ╚══════════════════════════════════════════════════════════════════════════════╝

def _run(cmd: list, timeout: int = 3) -> str:
    """Run a command, return stdout as string, empty on failure."""
    try:
        return subprocess.check_output(
            cmd, stderr=subprocess.DEVNULL, timeout=timeout
        ).decode("utf-8", errors="replace")
    except Exception:
        return ""


def get_wifi_ssid() -> Optional[str]:
    """Return current WiFi SSID or None."""
    try:
        if _SYSTEM == "Windows":
            out = _run(["netsh", "wlan", "show", "interfaces"], timeout=3)
            # Find "SSID" line but not "BSSID"
            for line in out.splitlines():
                m = re.match(r"\s+SSID\s*:\s*(.+)", line)
                if m and not line.strip().startswith("BSSID"):
                    ssid = m.group(1).strip()
                    if ssid:
                        return ssid
        elif _SYSTEM == "Darwin":
            out = _run([
                "/System/Library/PrivateFrameworks/Apple80211.framework"
                "/Versions/Current/Resources/airport", "-I"
            ])
            m = re.search(r"\s+SSID:\s*(.+)", out)
            if m:
                return m.group(1).strip()
        else:
            out = _run(["iwgetid", "-r"])
            return out.strip() or None
    except Exception as e:
        logger.debug(f"[SysMon] WiFi error: {e}")
    return None


def get_usb_devices() -> List[str]:
    """Return list of USB device name strings (max 6)."""
    devices = []
    try:
        if _SYSTEM == "Windows":
            # Use WMIC for friendly device names
            out = _run(["wmic", "path", "Win32_PnPEntity",
                        "where", "PNPClass='USB'",
                        "get", "Name"], timeout=5)
            for line in out.splitlines()[1:]:
                name = line.strip()
                if name and len(name) > 3 and name.lower() not in ("name", ""):
                    devices.append(name[:32])
                if len(devices) >= 6:
                    break
        elif _SYSTEM == "Darwin":
            out = _run(["system_profiler", "SPUSBDataType", "-detailLevel", "mini"],
                       timeout=5)
            names = re.findall(r"\n\s{4}([A-Za-z][\w\s]+):", out)
            devices = [n.strip()[:32] for n in names[:6] if n.strip()]
        else:
            out = _run(["lsusb"])
            for line in out.splitlines()[:6]:
                m = re.search(r"ID \w+:\w+ (.+)", line)
                if m:
                    devices.append(m.group(1).strip()[:32])
    except Exception as e:
        logger.debug(f"[SysMon] USB error: {e}")
    return devices or []


def get_bluetooth_devices() -> List[str]:
    """Return list of paired/connected Bluetooth device names."""
    devices = []
    try:
        if _SYSTEM == "Windows":
            ps = (
                "Get-PnpDevice -Class Bluetooth | "
                "Where-Object {$_.Status -eq 'OK'} | "
                "Select-Object -ExpandProperty FriendlyName"
            )
            out = _run(["powershell", "-NoProfile", "-Command", ps], timeout=5)
            for line in out.strip().splitlines():
                name = line.strip()
                if (name and len(name) > 1
                        and "bluetooth" not in name.lower()
                        and "radio" not in name.lower()):
                    devices.append(name[:32])
        elif _SYSTEM == "Darwin":
            out = _run(["system_profiler", "SPBluetoothDataType",
                        "-detailLevel", "mini"], timeout=5)
            names = re.findall(r"([\w\s\-]+):\s*\n\s+Connected: Yes", out)
            devices = [n.strip()[:32] for n in names[:4]]
        else:
            out = _run(["bluetoothctl", "devices", "Connected"])
            for line in out.splitlines():
                m = re.search(r"Device \S+ (.+)", line)
                if m:
                    devices.append(m.group(1).strip()[:32])
    except Exception as e:
        logger.debug(f"[SysMon] Bluetooth error: {e}")
    return devices


def get_serial_port_count() -> int:
    """Count active serial/COM ports."""
    try:
        import serial.tools.list_ports   # type: ignore
        return len(list(serial.tools.list_ports.comports()))
    except ImportError:
        pass
    try:
        if _SYSTEM == "Windows":
            out = _run(["wmic", "path", "Win32_SerialPort", "get", "Name"])
            return max(0, len([l for l in out.strip().splitlines()[1:] if l.strip()]))
    except Exception:
        pass
    return 0


# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║  SystemMonitor QThread                                                       ║
# ╚══════════════════════════════════════════════════════════════════════════════╝

class SystemMonitor(QThread):
    """
    Runs in background QThread.
    Emits stats_ready every INTERVAL seconds — never blocks main thread.
    """
    INTERVAL = 1.5   # fast-poll seconds

    stats_ready = pyqtSignal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setDaemon =True
        self._running = True

        # Optional dependency flags
        self._has_psutil = False
        self._has_gputil = False

        try:
            import psutil
            self._has_psutil = True
        except ImportError:
            logger.warning("[SysMon] psutil not installed (pip install psutil)")

        try:
            import GPUtil   # type: ignore
            self._has_gputil = True
        except ImportError:
            pass

        # Network baseline
        self._prev_net = None
        self._prev_ts  = time.time()
        if self._has_psutil:
            import psutil
            try:
                self._prev_net = psutil.net_io_counters()
            except Exception:
                pass

        # Slow-poll device caches (updated by start_device_loop)
        self._cache_wifi:   Optional[str] = None
        self._cache_usb:    List[str]     = []
        self._cache_bt:     List[str]     = []
        self._cache_serial: int           = 0

        # Ping cache (updated by start_ping_loop)
        self._cached_ping: Optional[int] = None

    # ── Main fast-poll loop ────────────────────────────────────────────────────
    def run(self):
        while self._running:
            try:
                stats = self._collect()
                self.stats_ready.emit(stats)
            except Exception as e:
                logger.error(f"[SysMon] Collection error: {e}")
            time.sleep(self.INTERVAL)

    def stop(self):
        self._running = False
        self.wait(2000)

    # ── Data collection ───────────────────────────────────────────────────────
    def _collect(self) -> dict:
        stats = {
            "cpu_pct":      0.0,
            "ram_pct":      0.0,
            "ram_used_gb":  0.0,
            "ram_total_gb": 0.0,
            "vram_pct":     None,
            "vram_used_mb": None,
            "battery_pct":  None,
            "charging":     False,
            "net_connected": False,
            "ping_ms":      self._cached_ping,
            "dl_mbps":      0.0,
            "ul_mbps":      0.0,
            # Device caches
            "wifi_ssid":    self._cache_wifi,
            "usb_devices":  list(self._cache_usb),
            "bt_devices":   list(self._cache_bt),
            "serial_ports": self._cache_serial,
        }

        if not self._has_psutil:
            return stats

        import psutil

        # CPU (non-blocking — uses previous interval result)
        try:
            stats["cpu_pct"] = psutil.cpu_percent(interval=0)
        except Exception:
            pass

        # RAM
        try:
            mem = psutil.virtual_memory()
            stats["ram_pct"]      = mem.percent
            stats["ram_used_gb"]  = round(mem.used  / 1e9, 1)
            stats["ram_total_gb"] = round(mem.total / 1e9, 1)
        except Exception:
            pass

        # Battery
        try:
            bat = psutil.sensors_battery()
            if bat:
                stats["battery_pct"] = int(bat.percent)
                stats["charging"]    = bool(bat.power_plugged)
        except Exception:
            pass

        # Network throughput
        try:
            now_net = psutil.net_io_counters()
            now_ts  = time.time()
            if self._prev_net:
                elapsed = max(now_ts - self._prev_ts, 0.001)
                dl = (now_net.bytes_recv - self._prev_net.bytes_recv) / elapsed / 1e6
                ul = (now_net.bytes_sent - self._prev_net.bytes_sent) / elapsed / 1e6
                stats["dl_mbps"] = round(max(dl, 0), 2)
                stats["ul_mbps"] = round(max(ul, 0), 2)
            self._prev_net = now_net
            self._prev_ts  = now_ts
        except Exception:
            pass

        # Network connected
        try:
            ifaces = psutil.net_if_stats()
            stats["net_connected"] = any(
                v.isup for k, v in ifaces.items()
                if k.lower() not in ("lo", "loopback")
            )
        except Exception:
            pass

        # GPU (NVIDIA via GPUtil)
        if self._has_gputil:
            try:
                import GPUtil   # type: ignore
                gpus = GPUtil.getGPUs()
                if gpus:
                    g = gpus[0]
                    stats["vram_used_mb"] = round(g.memoryUsed)
                    stats["vram_pct"]     = round(g.memoryUtil * 100, 1)
            except Exception:
                pass

        return stats

    # ── Ping loop (every 5s in daemon thread) ─────────────────────────────────
    def start_ping_loop(self):
        def _loop():
            while self._running:
                try:
                    host = "8.8.8.8"
                    if _SYSTEM == "Windows":
                        cmd = ["ping", "-n", "1", "-w", "1000", host]
                    else:
                        cmd = ["ping", "-c", "1", "-W", "1", host]
                    out = subprocess.check_output(
                        cmd, stderr=subprocess.DEVNULL, timeout=2
                    ).decode("utf-8", errors="replace")
                    m = re.search(r"[Tt]ime[=<](\d+)", out)
                    self._cached_ping = int(m.group(1)) if m else None
                except Exception:
                    self._cached_ping = None
                time.sleep(5)

        threading.Thread(target=_loop, daemon=True, name="jarvis-ping").start()

    # ── Device loop (every 8s in daemon thread) ───────────────────────────────
    def start_device_loop(self):
        """
        Polls WiFi SSID, USB devices, Bluetooth, and serial ports every 8 seconds.
        Results cached; served on every fast-poll cycle without blocking.
        """
        def _loop():
            while self._running:
                try:
                    self._cache_wifi   = get_wifi_ssid()
                    self._cache_usb    = get_usb_devices()
                    self._cache_bt     = get_bluetooth_devices()
                    self._cache_serial = get_serial_port_count()
                except Exception as e:
                    logger.debug(f"[SysMon] Device poll error: {e}")
                time.sleep(8)

        threading.Thread(target=_loop, daemon=True, name="jarvis-devices").start()
        logger.info("[SysMon] Device poll loop started (WiFi/USB/BT every 8s)")
