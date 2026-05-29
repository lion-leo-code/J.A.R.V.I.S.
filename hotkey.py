"""
JARVIS Hotkey Listener
Runs in a daemon thread. When triggered, emits app_signals.hotkey_triggered.
NEVER touches any Qt widget directly — that was the source of all crashes.
"""

import threading
import logging
import time

logger = logging.getLogger("jarvis.hotkey")


class HotkeyListener:
    """
    Listens globally for the configured trigger key combo.
    On activation → emits AppSignals.hotkey_triggered (thread-safe pyqtSignal).
    The main Qt thread receives this and calls toggle_visibility as a proper slot.
    """

    def __init__(self, trigger: str, signals):
        self.trigger  = trigger.lower().strip()
        self.signals  = signals
        self._lock    = threading.Lock()
        self._last_ts = 0.0
        self._running = True

    def start(self):
        """Blocking loop — must be called from a daemon thread."""
        logger.info(f"[Hotkey] Waiting for: {self.trigger}")
        try:
            import keyboard
            keyboard.add_hotkey(
                self.trigger,
                self._fire,
                suppress=False,
                trigger_on_release=False,
            )
            keyboard.wait()
        except ImportError:
            logger.warning("[Hotkey] `keyboard` not installed — using pynput fallback")
            self._pynput_loop()
        except Exception as e:
            logger.error(f"[Hotkey] {e} — using pynput fallback")
            self._pynput_loop()

    def _fire(self):
        """Debounce then emit signal. Zero UI code allowed here."""
        now = time.monotonic()
        with self._lock:
            if now - self._last_ts < 0.35:
                return
            self._last_ts = now
        logger.debug("[Hotkey] Triggered → emitting signal")
        # pyqtSignal.emit() is thread-safe in PyQt6.
        # Qt delivers it to the main thread via the event loop (QueuedConnection).
        self.signals.hotkey_triggered.emit()

    def stop(self):
        self._running = False
        try:
            import keyboard
            keyboard.unhook_all()
        except Exception:
            pass

    def _pynput_loop(self):
        try:
            from pynput import keyboard as pk
        except ImportError:
            logger.error("[Hotkey] Neither `keyboard` nor `pynput` installed.")
            return

        parts = self.trigger.split("+")
        key_map = {
            "ctrl":  (pk.Key.ctrl_l, pk.Key.ctrl_r),
            "alt":   (pk.Key.alt_l,  pk.Key.alt_r),
            "shift": (pk.Key.shift_l,pk.Key.shift_r),
            "win":   (pk.Key.cmd,),
            "cmd":   (pk.Key.cmd,),
            "super": (pk.Key.cmd,),
        }
        mod_keys: set = set()
        target = None

        for part in parts:
            part = part.strip()
            if part in key_map:
                mod_keys.update(key_map[part])
            else:
                try:
                    target = pk.KeyCode.from_char(part)
                except Exception:
                    try:
                        target = getattr(pk.Key, part)
                    except AttributeError:
                        target = pk.KeyCode.from_char(part[0] if part else "f")

        pressed: set = set()

        def _n(k):
            for a, b in [(pk.Key.ctrl_l, pk.Key.ctrl_r),
                         (pk.Key.alt_l,  pk.Key.alt_r),
                         (pk.Key.shift_l,pk.Key.shift_r)]:
                if k in (a, b): return a
            return k

        def on_press(k):
            pressed.add(_n(k))
            nm = {_n(m) for m in mod_keys}
            if mod_keys:
                if nm.issubset(pressed) and (target is None or _n(k) == _n(target)):
                    self._fire()
            elif target and _n(k) == _n(target):
                self._fire()

        def on_release(k):
            pressed.discard(_n(k))

        with pk.Listener(on_press=on_press, on_release=on_release) as l:
            l.join()
