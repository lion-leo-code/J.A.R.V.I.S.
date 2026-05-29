"""
JARVIS System Tray
QSystemTrayIcon with Open / Exit menu.
Clicking the icon emits hotkey_triggered (same signal as keyboard shortcut).
"""

import logging
from PyQt6.QtWidgets import QSystemTrayIcon, QMenu, QApplication
from PyQt6.QtGui     import QIcon, QPixmap, QPainter, QColor, QPen, QBrush
from PyQt6.QtCore    import QSize, Qt, pyqtSlot

logger = logging.getLogger("jarvis.tray")


def _make_icon() -> QIcon:
    """Programmatically draw a gold 'J' icon — no image file needed."""
    size  = 34
    px    = QPixmap(size, size)
    px.fill(Qt.GlobalColor.transparent)

    p = QPainter(px)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)

    # Background circle
    p.setBrush(QBrush(QColor(119, 20, 20)))
    p.setPen(QPen(QColor(212, 175, 55), 1.5))
    p.drawEllipse(2, 2, size - 4, size - 4)

    # Gold "J"
    from PyQt6.QtGui import QFont
    f = QFont("Arial", 14, QFont.Weight.Bold)
    p.setFont(f)
    p.setPen(QPen(QColor(212, 175, 55)))
    p.drawText(px.rect(), Qt.AlignmentFlag.AlignCenter, "J")
    p.end()

    return QIcon(px)


class TrayIcon(QSystemTrayIcon):

    def __init__(self, signals, parent=None):
        super().__init__(_make_icon(), parent)
        self.signals = signals
        self.setToolTip("J.A.R.V.I.S.")
        self._build_menu()
        self.activated.connect(self._on_activated)
        logger.info("[Tray] System tray initialized")

    def _build_menu(self):
        menu = QMenu()
        menu.setStyleSheet("""
            QMenu {
                background: #0A1A2F;
                color: #D4AF37;
                border: 1px solid #D4AF37;
                font-size: 12px;
                padding: 4px;
            }
            QMenu::item:selected { background: #1a2f4f; }
            QMenu::separator { background: #2b2b2b; height: 1px; margin: 3px 8px; }
        """)

        open_action = menu.addAction("⬡  Open JARVIS")
        open_action.triggered.connect(self._toggle)

        menu.addSeparator()

        exit_action = menu.addAction("✕  Exit")
        exit_action.triggered.connect(QApplication.quit)

        self.setContextMenu(menu)

    def _on_activated(self, reason):
        if reason in (
            QSystemTrayIcon.ActivationReason.Trigger,
            QSystemTrayIcon.ActivationReason.DoubleClick,
        ):
            self._toggle()

    def _toggle(self):
        self.signals.hotkey_triggered.emit()
