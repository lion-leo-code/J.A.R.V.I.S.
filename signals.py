"""JARVIS Signal Bus — all cross-thread communication."""
from PyQt6.QtCore import QObject, pyqtSignal


class AppSignals(QObject):
    # Hotkey
    hotkey_triggered = pyqtSignal()

    # Brain / Processing
    status_update    = pyqtSignal(str)
    status_state     = pyqtSignal(str)      # "ready|listening|thinking|processing|error"
    step_update      = pyqtSignal(int, str, str)
    result_ready     = pyqtSignal(str, list)
    error_occurred   = pyqtSignal(str)

    # System Monitor → HUD
    stats_updated    = pyqtSignal(dict)

    # HUD visibility
    hud_show         = pyqtSignal()
    hud_hide         = pyqtSignal()

    # Safety confirmation (background → UI → background)
    confirm_request  = pyqtSignal(str)   # question text
    confirm_response = pyqtSignal(bool)  # True=yes, False=no

    # Voice input
    voice_text       = pyqtSignal(str)   # transcribed speech → pipeline

    # Ask for missing info mid-command
    ask_user         = pyqtSignal(str)   # prompt shown in HUD input area


app_signals = AppSignals()
