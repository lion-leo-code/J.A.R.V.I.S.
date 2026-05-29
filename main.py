"""
JARVIS — Main Entry Point
All data written to JARVIS_DIR = C:\\Users\\aniak\\Documents\\J.A.R.V.I.S
"""

import sys
import signal
import threading
import logging
import json
import os
import pathlib
from pathlib import Path

from PyQt6.QtWidgets import QApplication

# ═══════════════════════════════════════════════════════════════════════════════
# GLOBAL STORAGE DIRECTORY — ALL files live here, nowhere else
# ═══════════════════════════════════════════════════════════════════════════════
JARVIS_DIR = pathlib.Path(r"C:\Users\aniak\Documents\J.A.R.V.I.S")
JARVIS_DIR.mkdir(parents=True, exist_ok=True)

# Make JARVIS_DIR importable by all modules
import builtins
builtins.JARVIS_DIR = JARVIS_DIR


def _setup_logging():
    log_path = JARVIS_DIR / "jarvis.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(name)-22s  %(levelname)-7s  %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(str(log_path), encoding="utf-8"),
        ],
    )


def load_config() -> dict:
    """
    Load config.json from the script directory.
    Inject JARVIS_DIR-based paths so sub-modules get correct values.
    """
    cfg_path = Path(__file__).parent / "config.json"
    with open(cfg_path, encoding="utf-8") as f:
        cfg = json.load(f)

    # Override all storage paths to use JARVIS_DIR
    cfg["jarvis_dir"]       = str(JARVIS_DIR)
    cfg["memory"]["db_path"] = str(JARVIS_DIR / "memory.db")
    cfg["logging"]["file"]   = str(JARVIS_DIR / "jarvis.log")
    return cfg


def main():
    _setup_logging()
    config = load_config()
    logger = logging.getLogger("jarvis.main")
    logger.info(f"[Main] JARVIS_DIR = {JARVIS_DIR}")
    logger.info(f"[Main] JARVIS_DIR exists: {JARVIS_DIR.exists()}")

    # ── Qt application ────────────────────────────────────────────────────
    app = QApplication(sys.argv)
    app.setApplicationName("JARVIS")
    app.setQuitOnLastWindowClosed(False)

    # ── Signal bus ────────────────────────────────────────────────────────
    from signals import app_signals

    # ── Core subsystems ───────────────────────────────────────────────────
    from memory   import MemorySystem
    from tools    import ToolRegistry
    from safety   import SafetyLayer
    from executor import Executor
    from planner  import Planner
    from brain    import Brain

    memory   = MemorySystem(config["memory"]["db_path"])
    tools    = ToolRegistry(config)
    safety   = SafetyLayer(config["safety"])
    executor = Executor(tools, safety)
    executor.set_signals(app_signals)          # wire confirm/ask signals
    planner  = Planner(config)
    brain    = Brain(config, memory, planner, executor)

    # ── Full-screen HUD overlay ───────────────────────────────────────────
    from hud import HudOverlay
    hud_overlay = HudOverlay()
    app_signals.hud_show.connect(hud_overlay.show_hud)
    app_signals.hud_hide.connect(hud_overlay.hide_hud)

    # ── System monitor ────────────────────────────────────────────────────
    from system_monitor import SystemMonitor
    monitor = SystemMonitor()
    monitor.stats_ready.connect(app_signals.stats_updated)
    monitor.stats_ready.connect(hud_overlay.update_stats)
    monitor.start()
    monitor.start_ping_loop()
    monitor.start_device_loop()

    # ── Center command panel ──────────────────────────────────────────────
    from ui import JarvisHUD
    hud = JarvisHUD(brain, app_signals, config)

    # ── System tray ───────────────────────────────────────────────────────
    try:
        from tray import TrayIcon
        tray = TrayIcon(app_signals)
        tray.show()
    except Exception as e:
        logger.warning(f"[Main] Tray unavailable: {e}")

    # ── Global hotkey listener ────────────────────────────────────────────
    from hotkey import HotkeyListener
    listener  = HotkeyListener(config["hotkey"]["trigger"], app_signals)
    hk_thread = threading.Thread(target=listener.start, daemon=True, name="hotkey")
    hk_thread.start()

    # ── Optional immediate show ───────────────────────────────────────────
    if config.get("show_on_start", False):
        hud.toggle_visibility()

    signal.signal(signal.SIGINT, signal.SIG_DFL)
    logger.info(f"[Main] Online. Hotkey: {config['hotkey']['trigger']}")
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
