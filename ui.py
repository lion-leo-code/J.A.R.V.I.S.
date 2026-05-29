"""
JARVIS Command Panel â€” v4
Critical fixes:
  â€¢ Stuck-thinking bug: thread cleanup order fixed + 15s watchdog (12s LLM + 3s)
  â€¢ Response timer: estimate shown before, actual shown after
  â€¢ [JARVIS]-> prefix stripped from all responses
  â€¢ Cyber blue (#00E5FF) color scheme
  â€¢ Pixel-style gold JARVIS logo drawn with QPainter
  â€¢ Clean natural response output
"""
import os; os.environ["QT_AUTO_SCREEN_SCALE_FACTOR"] = "1"

import os
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QGuiApplication

# Critical fix for your 1600p display
os.environ["QT_AUTO_SCREEN_SCALE_FACTOR"] = "1"
QGuiApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)

import json
import math
import random
import re
import time
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLineEdit,
    QScrollArea, QLabel, QSizePolicy, QApplication, QFrame
)
from PyQt6.QtCore import (
    Qt, QTimer, QPropertyAnimation, QEasingCurve,
    QRect, pyqtSignal, QThread, QObject, pyqtSlot, QPointF
)
from PyQt6.QtGui import (
    QPainter, QColor, QPen, QBrush, QLinearGradient,
    QPainterPath, QRadialGradient, QFont, QPolygon
)

# â”€â”€ Cyber palette â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
C_BLUE      = QColor(  0, 229, 255)   # #00E5FF  cyber blue primary
C_BLUE_DIM  = QColor(  0, 180, 210, 140)
C_BLUE_GLOW = QColor(  0, 229, 255,  40)
C_GREEN     = QColor(  0, 255,  65)   # #00FF41  neon green accent
C_GOLD      = QColor(212, 175,  55)   # #D4AF37  gold
C_GOLD2     = QColor(255, 220,  90)   # bright gold highlight
C_GOLD3     = QColor(160, 120,  15)   # dark gold
C_GOLD_DIM  = QColor(212, 175,  55,  55)
C_WHITE     = QColor(255, 255, 255)
C_CHARCOAL  = QColor( 30,  30,  40)
C_TEXT      = QColor(200, 230, 255)   # cool white text
C_SUB       = QColor( 80, 130, 160)
C_SUCCESS   = QColor( 80, 200, 120)
C_ERROR     = QColor(220,  60,  60)

STATE_COLORS = {
    "ready":      QColor( 0, 229, 255),   # cyber blue
    "listening":  QColor( 0, 230, 230),   # cyan
    "thinking":   QColor(220, 200,   0),  # yellow
    "processing": QColor(255, 140,   0),  # orange
    "error":      QColor(220,  60,  60),  # red
}

WIN_W = 680
WIN_H = 420

# Response time estimation (seconds per word of output, rough heuristic)
AVG_WORDS_PER_SEC = 8.0


# â”€â”€ Gold pixel letter definitions (7Ã—9 grid, 0=off 1=on) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# Each letter is a list of (x, y) filled pixel coordinates in a 7-wide grid
_PIXEL_FONT = {
    'J': [(3,0),(4,0),(5,0),(3,1),(4,1),(5,1),(4,2),(4,3),(4,4),
          (4,5),(0,6),(4,6),(0,7),(1,7),(2,7),(3,7),(4,7)],
    'A': [(2,0),(3,0),(1,1),(4,1),(0,2),(5,2),(0,3),(5,3),
          (0,4),(1,4),(2,4),(3,4),(4,4),(5,4),(0,5),(5,5),(0,6),(5,6)],
    'R': [(0,0),(1,0),(2,0),(3,0),(0,1),(4,1),(0,2),(4,2),
          (0,3),(1,3),(2,3),(3,3),(0,4),(2,4),(0,5),(3,5),(0,6),(4,6)],
    'V': [(0,0),(5,0),(0,1),(5,1),(0,2),(5,2),(1,3),(4,3),
          (1,4),(4,4),(2,5),(3,5),(2,6),(3,6)],
    'I': [(0,0),(1,0),(2,0),(3,0),(4,0),(2,1),(2,2),(2,3),
          (2,4),(2,5),(0,6),(1,6),(2,6),(3,6),(4,6)],
    'S': [(1,0),(2,0),(3,0),(4,0),(0,1),(0,2),(1,3),(2,3),(3,3),
          (4,4),(4,5),(0,6),(1,6),(2,6),(3,6)],
}


# â”€â”€ Particle â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
class Particle:
    def __init__(self, cx: float, cy: float):
        angle  = random.uniform(0, 2 * math.pi)
        radius = random.uniform(85, 170)
        speed  = random.uniform(0.2, 0.65)
        self.x = cx + math.cos(angle) * radius
        self.y = cy + math.sin(angle) * radius
        self.vx = math.cos(angle + math.pi / 2) * speed * random.choice([-1, 1])
        self.vy = math.sin(angle + math.pi / 2) * speed * random.choice([-1, 1]) * 0.6 - 0.08
        self.life  = random.uniform(0.5, 1.0)
        self.decay = random.uniform(0.004, 0.009)
        self.size  = random.uniform(1.0, 2.5)
        self.gold  = random.random() > 0.4   # 60% gold, 40% blue

    def tick(self):
        self.x    += self.vx
        self.y    += self.vy
        self.life -= self.decay
        return self.life > 0


# â”€â”€ Brain Worker â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
class BrainWorker(QObject):
    status_update = pyqtSignal(str)
    step_update   = pyqtSignal(int, str, str)
    result_ready  = pyqtSignal(str, list)
    error         = pyqtSignal(str)
    finished      = pyqtSignal()

    def __init__(self, brain, command: str):
        super().__init__()
        self.brain   = brain
        self.command = command

    @pyqtSlot()
    def run(self):
        try:
            self.brain.process(
                self.command,
                on_status = self.status_update.emit,
                on_step   = self.step_update.emit,
                on_done   = lambda r, s: self.result_ready.emit(r, s),
            )
        except Exception as e:
            self.error.emit(str(e))
        finally:
            # finished MUST fire even if everything else fails
            self.finished.emit()


# â”€â”€ Ring Widget â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
class RingWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._phase   = 0.0
        self._active  = False
        self._opacity = 0.0
        self._state   = "ready"
        self._rot     = 0.0   # rotation angle for outer ring

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(40)

    def set_active(self, v: bool):  self._active = v
    def set_state(self, s: str):    self._state = s
    def set_opacity(self, v: float):
        self._opacity = max(0.0, min(1.0, v))
        self.update()

    def _tick(self):
        self._phase = (self._phase + 0.022) % (2 * math.pi)
        self._rot   = (self._rot + 0.8) % 360
        self.update()

    def paintEvent(self, _e):
        if self._opacity < 0.02: return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        cx, cy = self.width() // 2, self.height() // 2
        clr = STATE_COLORS.get(self._state, C_BLUE) if not self._active else C_GOLD

        # Concentric pulsing rings
        for i, (br, sp) in enumerate([(90, 1.0), (118, 0.65), (148, 0.4)]):
            pulse = math.sin(self._phase * sp + i * 1.2) * 5
            r     = br + pulse
            a     = int((0.30 - i * 0.07) * self._opacity * 255)
            pen   = QPen(QColor(clr.red(), clr.green(), clr.blue(), a), 1.2)
            p.setPen(pen); p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(int(cx - r), int(cy - r), int(r * 2), int(r * 2))

        # Outer rotating dashed ring
        p.save()
        p.translate(cx, cy)
        p.rotate(self._rot)
        dash_a = int(55 * self._opacity)
        dash_pen = QPen(QColor(clr.red(), clr.green(), clr.blue(), dash_a), 1.0)
        dash_pen.setStyle(Qt.PenStyle.DashLine)
        p.setPen(dash_pen); p.setBrush(Qt.BrushStyle.NoBrush)
        outer_r = 162
        p.drawEllipse(-outer_r, -outer_r, outer_r * 2, outer_r * 2)
        p.restore()

        # Scan line when active
        if self._active:
            sa = int(abs(math.sin(self._phase * 1.5)) * 60 * self._opacity)
            sy = int(math.sin(self._phase * 0.8) * 80)
            p.setPen(QPen(QColor(212, 175, 55, sa), 1.0))
            p.drawLine(cx - 145, cy + sy, cx + 145, cy + sy)
        p.end()


# â”€â”€ Step Item â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
class StepItem(QWidget):
    def __init__(self, index: int, text: str, parent=None):
        super().__init__(parent)
        self.setFixedHeight(27)
        self._phase = 0.0
        lo = QHBoxLayout(self)
        lo.setContentsMargins(4, 0, 4, 0)
        lo.setSpacing(7)

        self._dot = QLabel("â—‹")
        self._dot.setFixedWidth(13)
        self._dot.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._dot.setStyleSheet(f"color:{C_SUB.name()}; font-size:9px;")

        num = QLabel(f"{index+1:02d}")
        num.setFixedWidth(18)
        num.setStyleSheet(f"color:{C_BLUE.name()}; font-size:9px; font-weight:bold;")

        self._lbl = QLabel(text)
        self._lbl.setStyleSheet(f"color:{C_TEXT.name()}; font-size:11px; font-family:'Courier New';")

        lo.addWidget(self._dot); lo.addWidget(num)
        lo.addWidget(self._lbl); lo.addStretch()

        self._at = QTimer(self)
        self._at.timeout.connect(self._tick)

    def set_status(self, s: str):
        if s == "running":
            self._at.start(80)
            self._dot.setStyleSheet(f"color:{C_BLUE.name()}; font-size:9px;")
            self._lbl.setStyleSheet(f"color:{C_WHITE.name()}; font-size:11px; font-family:'Courier New';")
        elif s == "done":
            self._at.stop()
            self._dot.setText("âœ“")
            self._dot.setStyleSheet(f"color:{C_SUCCESS.name()}; font-size:9px;")
            self._lbl.setStyleSheet(f"color:{C_SUB.name()}; font-size:11px; font-family:'Courier New';")
        elif s == "error":
            self._at.stop()
            self._dot.setText("âœ—")
            self._dot.setStyleSheet(f"color:{C_ERROR.name()}; font-size:9px;")
            self._lbl.setStyleSheet(f"color:{C_ERROR.name()}; font-size:11px; font-family:'Courier New';")

    def _tick(self):
        self._phase += 0.4
        self._dot.setText(["â—","â—“","â—‘","â—’"][int(self._phase) % 4])


# â”€â”€ Main Command Panel â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
class JarvisHUD(QWidget):

    def __init__(self, brain, signals, config):
        super().__init__()
        self.brain       = brain
        self.signals     = signals
        self.config      = config
        self._visible    = False
        self._processing = False
        self._step_widgets: list = []
        self._state      = "ready"
        self._start_ts   = 0.0      # command start timestamp
        self._est_time   = 0.0      # estimated response time

        # Particles
        self._particles: list = []

        self._setup_window()
        self._build_ui()
        self._setup_animations()
        self._connect_signals()

    def _setup_window(self):
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint  |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        screen = QApplication.primaryScreen()
        geo    = screen.availableGeometry() if screen else QRect(0, 0, 1920, 1080)
        x = (geo.width()  - WIN_W) // 2
        y = (geo.height() - WIN_H) // 2 - 20
        self.setGeometry(x, y, WIN_W, WIN_H)
        self.setFixedSize(WIN_W, WIN_H)

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(32, 22, 32, 16)
        root.setSpacing(0)

        self._rings = RingWidget(self)
        self._rings.setGeometry(0, 0, WIN_W, WIN_H)
        self._rings.lower()

        # â”€â”€ Header â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        hdr = QHBoxLayout(); hdr.setSpacing(0)
        self._title_ph = QWidget()
        self._title_ph.setFixedSize(230, 28)
        self._title_ph.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        self._status_dot = QLabel("â—")
        self._status_dot.setStyleSheet(
            f"color:{STATE_COLORS['ready'].name()}; font-size:9px;")
        self._status_lbl = QLabel("READY")
        self._status_lbl.setStyleSheet(
            f"color:{C_SUB.name()}; font-size:9px; letter-spacing:2px; font-family:'Courier New';")

        hdr.addWidget(self._title_ph)
        hdr.addStretch()
        hdr.addWidget(self._status_dot); hdr.addSpacing(5)
        hdr.addWidget(self._status_lbl)

        # â”€â”€ Divider â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        div = QWidget(); div.setFixedHeight(1)
        div.setStyleSheet(f"background: qlineargradient(x1:0,y1:0,x2:1,y2:0,"
                          f"stop:0 {C_BLUE.name()}, stop:0.5 {C_GOLD_DIM.name()}, stop:1 transparent);")

        # â”€â”€ Timing label â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        self._time_lbl = QLabel("")
        self._time_lbl.setStyleSheet(
            f"color:{C_SUB.name()}; font-size:9px; font-family:'Courier New';")
        self._time_lbl.setAlignment(Qt.AlignmentFlag.AlignRight)

        # â”€â”€ Input â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        inp_row = QHBoxLayout()
        inp_row.setContentsMargins(0, 10, 0, 4)
        inp_row.setSpacing(8)

        prompt = QLabel("â€º")
        prompt.setStyleSheet(
            f"color:{C_BLUE.name()}; font-size:18px; font-weight:bold;")

        self._input = QLineEdit()
        self._input.setPlaceholderText("Issue a commandâ€¦")
        self._input.setStyleSheet(f"""
            QLineEdit {{
                background: transparent;
                border: none;
                color: {C_WHITE.name()};
                font-size: 13px;
                font-family: "Courier New";
                letter-spacing: 0.5px;
                padding: 2px 0;
                selection-background-color: {C_BLUE_DIM.name()};
            }}
        """)
        self._input.returnPressed.connect(self._submit)

        # Voice button
        self._voice_btn = QLabel("ðŸŽ¤")
        self._voice_btn.setFixedSize(22, 22)
        self._voice_btn.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._voice_btn.setStyleSheet(f"color:{C_SUB.name()}; font-size:13px;")
        self._voice_btn.setToolTip("Voice input (click to speak)")
        self._voice_btn.mousePressEvent = lambda _e: self._start_voice()
        _voice_on = self.config.get("voice", {}).get("input_enabled", False)
        self._voice_btn.setVisible(_voice_on)

        inp_row.addWidget(prompt)
        inp_row.addWidget(self._input)
        inp_row.addWidget(self._voice_btn)

        # â”€â”€ Output scroll â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setStyleSheet(f"""
            QScrollArea {{ background: transparent; border: none; }}
            QScrollBar:vertical {{
                background: {C_CHARCOAL.name()}; width: 3px; border-radius: 1px;
            }}
            QScrollBar::handle:vertical {{
                background: {C_BLUE_DIM.name()}; border-radius: 1px; min-height: 20px;
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
        """)
        self._out_widget = QWidget()
        self._out_widget.setStyleSheet("background: transparent;")
        self._out_layout = QVBoxLayout(self._out_widget)
        self._out_layout.setContentsMargins(0, 0, 4, 0)
        self._out_layout.setSpacing(2)
        self._out_layout.addStretch()
        self._scroll.setWidget(self._out_widget)

        # â”€â”€ Confirmation bar (hidden until needed) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        self._confirm_bar = QWidget()
        self._confirm_bar.setStyleSheet(
            "background: rgba(0,20,40,200); border-radius:6px;")
        self._confirm_bar.setFixedHeight(38)
        self._confirm_bar.setVisible(False)
        cb_lay = QHBoxLayout(self._confirm_bar)
        cb_lay.setContentsMargins(8, 4, 8, 4)
        cb_lay.setSpacing(8)
        self._confirm_lbl = QLabel("")
        self._confirm_lbl.setStyleSheet(
            f"color:{C_TEXT.name()}; font-size:10px; font-family:'Courier New';")
        self._confirm_lbl.setWordWrap(False)
        btn_yes = QLabel("  YES  ")
        btn_yes.setStyleSheet(
            f"color:{C_SUCCESS.name()}; font-size:9px; font-weight:bold; "
            f"font-family:'Courier New'; border:1px solid {C_SUCCESS.name()}; "
            "border-radius:3px; padding:2px 6px;")
        btn_yes.mousePressEvent = lambda _e: self._confirm_answer(True)
        btn_no = QLabel("  NO  ")
        btn_no.setStyleSheet(
            f"color:{C_ERROR.name()}; font-size:9px; font-weight:bold; "
            f"font-family:'Courier New'; border:1px solid {C_ERROR.name()}; "
            "border-radius:3px; padding:2px 6px;")
        btn_no.mousePressEvent = lambda _e: self._confirm_answer(False)
        cb_lay.addWidget(self._confirm_lbl)
        cb_lay.addStretch()
        cb_lay.addWidget(btn_yes)
        cb_lay.addWidget(btn_no)

        # â”€â”€ Footer â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        fdiv = QWidget(); fdiv.setFixedHeight(1)
        fdiv.setStyleSheet(f"background:{C_CHARCOAL.name()};")
        foot = QHBoxLayout()
        foot.setContentsMargins(0, 5, 0, 0)
        hk = self.config.get("hotkey", {}).get("trigger", "ctrl+space").upper()
        hint = QLabel(f"ESC  dismiss  Â·  ENTER  send  Â·  {hk}  toggle")
        hint.setStyleSheet(
            f"color:{C_SUB.name()}; font-size:8px; letter-spacing:1px; font-family:'Courier New';")
        foot.addStretch(); foot.addWidget(hint)

        root.addLayout(hdr)
        root.addSpacing(6)
        root.addWidget(div)
        root.addWidget(self._time_lbl)
        root.addLayout(inp_row)
        root.addWidget(self._scroll)
        root.addWidget(self._confirm_bar)
        root.addSpacing(4)
        root.addWidget(fdiv)
        root.addLayout(foot)

    def _setup_animations(self):
        self._fade_anim = QPropertyAnimation(self, b"windowOpacity")
        self._fade_anim.setDuration(200)
        self._fade_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        self._blink_timer = QTimer(self)
        self._blink_timer.timeout.connect(self._blink)
        self._blink_state = False

        self._think_timer = QTimer(self)
        self._think_timer.timeout.connect(self._tick_thinking)
        self._think_dots  = 0

        # WATCHDOG: forces _worker_done after timeout if thread hangs
        self._watchdog = QTimer(self)
        self._watchdog.setSingleShot(True)
        self._watchdog.timeout.connect(self._on_watchdog)

        # Particle timer
        self._part_timer = QTimer(self)
        self._part_timer.timeout.connect(self._tick_particles)
        self._part_timer.start(40)

    def _connect_signals(self):
        self.signals.hotkey_triggered.connect(self.toggle_visibility)
        self.signals.status_update.connect(self._on_status_update)
        self.signals.status_state.connect(self._on_status_state)
        self.signals.step_update.connect(self._on_step_update)
        self.signals.result_ready.connect(self._on_result)
        self.signals.error_occurred.connect(self._on_error)
        self.signals.confirm_request.connect(self._on_confirm_request)
        self.signals.voice_text.connect(self._on_voice_text)
        self.signals.ask_user.connect(self._on_ask_user)

    # â”€â”€ Toggle â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    @pyqtSlot()
    def toggle_visibility(self):
        self._hide() if self._visible else self._show()

    def _show(self):
        if self._visible: return
        self._visible = True
        self.setWindowOpacity(0.0)
        self.show(); self.raise_(); self.activateWindow()
        self._rings.set_opacity(0.0)
        self._fade_anim.stop()
        self._fade_anim.setStartValue(0.0)
        self._fade_anim.setEndValue(1.0)
        self._fade_anim.start()
        self._fade_rings(0.0, 1.0)
        self._input.setFocus()
        self._apply_state("ready")
        self.signals.hud_show.emit()

    def _hide(self):
        if not self._visible: return
        self._visible = False
        self._fade_anim.stop()
        self._fade_anim.setStartValue(self.windowOpacity())
        self._fade_anim.setEndValue(0.0)
        self._fade_anim.finished.connect(self.__finish_hide)
        self._fade_anim.start()
        self.signals.hud_hide.emit()

    def __finish_hide(self):
        try: self._fade_anim.finished.disconnect(self.__finish_hide)
        except Exception: pass
        self.hide()

    def _fade_rings(self, start, end):
        delta = (end - start) / 18; cur = [start]
        def _s():
            cur[0] = max(0.0, min(1.0, cur[0] + delta))
            self._rings.set_opacity(cur[0])
            if abs(cur[0] - end) > 0.02: QTimer.singleShot(12, _s)
        QTimer.singleShot(12, _s)

    # â”€â”€ State â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    def _apply_state(self, state: str):
        self._state = state
        clr   = STATE_COLORS.get(state, C_BLUE)
        labels = {"ready":"READY","listening":"LISTENING",
                  "thinking":"THINKING","processing":"PROCESSING","error":"ERROR"}
        self._status_dot.setStyleSheet(f"color:{clr.name()}; font-size:9px;")
        self._status_lbl.setText(labels.get(state, state.upper()))
        self._rings.set_state(state)
        self._blink_timer.stop()

    @pyqtSlot(str)
    def _on_status_state(self, s: str): self._apply_state(s)

    @pyqtSlot(str)
    def _on_status_update(self, text: str):
        t = text.lower()
        if "think" in t or "plan" in t: self._apply_state("thinking")
        elif "process" in t or "step" in t: self._apply_state("processing")
        elif "listen" in t: self._apply_state("listening")
        else: self._status_lbl.setText(text.upper()[:20])

    def _blink(self):
        self._blink_state = not self._blink_state
        clr = STATE_COLORS.get(self._state, C_BLUE)
        c = clr.name() if self._blink_state else "transparent"
        self._status_dot.setStyleSheet(f"color:{c}; font-size:9px;")

    def _tick_thinking(self):
        self._think_dots = (self._think_dots + 1) % 4
        lbl = {"thinking":"THINKING","processing":"PROCESSING"}.get(self._state,"WORKING")
        self._status_lbl.setText(lbl + "." * self._think_dots)

    # â”€â”€ Particles â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    def _tick_particles(self):
        if random.random() < 0.22 and len(self._particles) < 24:
            self._particles.append(Particle(WIN_W / 2, WIN_H / 2))
        self._particles = [p for p in self._particles if p.tick()]
        if self._visible: self.update()

    # â”€â”€ Submit â€” FIXED threading â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    def _submit(self):
        cmd = self._input.text().strip()
        if not cmd or self._processing: return

        self._input.clear()
        self._processing = True
        self._start_ts   = time.monotonic()
        self._clear_output()
        self._rings.set_active(True)
        self._add_bubble(cmd, "user")
        self._apply_state("thinking")
        self._blink_timer.start(420)
        self._think_timer.start(360)
        self.signals.status_state.emit("thinking")

        # Estimate: use brain's actual configured LLM timeout
        llm_t = getattr(self.brain, '_timeout', 12)
        est   = float(llm_t) if (
            hasattr(self.brain, '_ollama_online') and self.brain._ollama_online
        ) else 0.8
        self._est_time = est
        self._time_lbl.setText(f"â± Est. â‰¤{est:.0f}s")

        # Correct cleanup order: worker.finished â†’ thread.quit â†’ deleteLater â†’ _worker_done
        self._active_thread = QThread()
        self._active_worker = BrainWorker(self.brain, cmd)
        self._active_worker.moveToThread(self._active_thread)

        self._active_thread.started.connect(self._active_worker.run)

        # Worker signals â†’ app signals (cross-thread, queued)
        self._active_worker.status_update.connect(self.signals.status_update)
        self._active_worker.step_update.connect(self.signals.step_update)
        self._active_worker.result_ready.connect(self.signals.result_ready)
        self._active_worker.error.connect(self.signals.error_occurred)

        self._active_worker.finished.connect(self._active_thread.quit)
        self._active_thread.finished.connect(self._active_worker.deleteLater)
        self._active_thread.finished.connect(self._active_thread.deleteLater)
        self._active_thread.finished.connect(self._worker_done)

        # Watchdog: LLM timeout (12s) + 3s executor buffer
        watchdog_ms = (llm_t + 3) * 1000
        self._watchdog.start(int(watchdog_ms))

        self._active_thread.start()

    def _on_watchdog(self):
        """Force-complete if worker never finishes."""
        if self._processing:
            self._add_bubble("Task timed out after 12 seconds. Check that Ollama is running: ollama serve", "error")
            self._worker_done()

    def _worker_done(self):
        if not self._processing: return   # guard against double-call
        self._watchdog.stop()
        elapsed = time.monotonic() - self._start_ts
        self._processing = False
        self._think_timer.stop()
        self._blink_timer.stop()
        self._rings.set_active(False)
        self._apply_state("ready")
        self.signals.status_state.emit("ready")
        self._input.setFocus()
        # Show actual timing
        self._time_lbl.setText(f"â± Est. {self._est_time:.1f}s  Â·  Actual {elapsed:.2f}s")

    # â”€â”€ Slot handlers â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    @pyqtSlot(int, str, str)
    def _on_step_update(self, idx: int, text: str, status: str):
        if status == "init":
            w = StepItem(idx, text)
            w.setStyleSheet("background: transparent;")
            self._step_widgets.append(w)
            self._out_layout.insertWidget(self._out_layout.count() - 1, w)
            w.show()
        elif idx < len(self._step_widgets):
            self._step_widgets[idx].set_status(status)
        self._scroll_bottom()

    @pyqtSlot(str, list)
    def _on_result(self, response: str, _steps: list):
        clean = self._sanitize_output(response)
        self._add_bubble(clean, "assistant")

    @pyqtSlot(str)
    def _on_error(self, err: str):
        self._apply_state("error")
        self._add_bubble(f"System error: {err}", "error")

    # â”€â”€ Output â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    def _clear_output(self):
        self._step_widgets.clear()
        while self._out_layout.count() > 1:
            item = self._out_layout.takeAt(0)
            if item and item.widget(): item.widget().deleteLater()

    def _add_bubble(self, text: str, role: str):
        text = self._sanitize_output(text)
        if not text:
            return
        c = QWidget(); c.setStyleSheet("background:transparent;")
        lo = QVBoxLayout(c); lo.setContentsMargins(0, 2, 0, 2)

        if role == "user":
            pc, tc, prefix = C_GOLD.name(), C_GOLD.name(), "YOU"
        elif role == "error":
            pc, tc, prefix = C_ERROR.name(), C_ERROR.name(), "ERROR"
        else:
            pc, tc, prefix = C_BLUE.name(), C_TEXT.name(), "JARVIS"

        ph = QLabel(prefix)
        ph.setStyleSheet(
            f"color:{pc}; font-size:8px; font-weight:bold; "
            f"letter-spacing:2px; font-family:'Courier New';")
        tl = QLabel(text)
        tl.setWordWrap(True)
        tl.setStyleSheet(
            f"color:{tc}; font-size:12px; font-family:'Courier New'; line-height:1.5;")
        tl.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        lo.addWidget(ph); lo.addWidget(tl)
        self._out_layout.insertWidget(self._out_layout.count() - 1, c)
        c.show()
        self._scroll_bottom()

    def _scroll_bottom(self):
        QTimer.singleShot(40, lambda: self._scroll.verticalScrollBar().setValue(
            self._scroll.verticalScrollBar().maximum()))
    def _sanitize_output(self, text: str) -> str:
        if text is None:
            return ""

        clean = str(text).strip()
        if not clean:
            return ""

        try:
            parsed = json.loads(clean)
            if isinstance(parsed, dict):
                if isinstance(parsed.get("output"), str):
                    clean = parsed["output"].strip()
                elif parsed.get("prompt"):
                    clean = str(parsed["prompt"]).strip()
                elif parsed.get("summary"):
                    clean = str(parsed["summary"]).strip()
                else:
                    clean = ""
        except Exception:
            pass

        clean = re.sub(r"^```(?:[\w+-]+)?\s*", "", clean, flags=re.IGNORECASE)
        clean = re.sub(r"\s*```$", "", clean).strip()
        clean = re.sub(r"^\[?JARVIS\]?\s*[-:>]+\s*", "", clean, flags=re.IGNORECASE)

        if clean.startswith("{") and clean.endswith("}"):
            try:
                parsed = json.loads(clean)
                if isinstance(parsed, dict):
                    clean = str(parsed.get("output") or parsed.get("prompt") or parsed.get("summary") or "").strip()
            except Exception:
                clean = ""

        return clean


    # â”€â”€ Paint â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        w, h, r = self.width(), self.height(), 13

        # Glass background â€” deep black with blue tint at top
        bg = QLinearGradient(0, 0, 0, h)
        bg.setColorAt(0.0, QColor(  5, 18, 32, 238))
        bg.setColorAt(0.3, QColor(  3, 10, 18, 225))
        bg.setColorAt(1.0, QColor(  2,  6, 12, 235))
        p.setBrush(QBrush(bg)); p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(2, 2, w - 4, h - 4, r, r)

        # Cyber blue border
        bgrad = QLinearGradient(0, 0, w, h)
        bgrad.setColorAt(0.0, QColor(  0, 229, 255, 160))
        bgrad.setColorAt(0.4, QColor(  0, 229, 255,  40))
        bgrad.setColorAt(0.7, QColor(212, 175,  55,  80))
        bgrad.setColorAt(1.0, QColor(  0, 229, 255, 120))
        p.setPen(QPen(QBrush(bgrad), 1.2)); p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(1, 1, w - 2, h - 2, r, r)

        # Inner subtle glow line at top
        sheen = QLinearGradient(0, 0, 0, 40)
        sheen.setColorAt(0.0, QColor(0, 229, 255, 18))
        sheen.setColorAt(1.0, QColor(0, 229, 255,  0))
        p.setBrush(QBrush(sheen)); p.setPen(Qt.PenStyle.NoPen)
        pp = QPainterPath()
        pp.addRoundedRect(2, 2, w - 4, 40, r, r)
        p.drawPath(pp)

        # Corner L-accents â€” cyber blue
        cl = 18
        cp = QPen(C_BLUE, 1.6)
        p.setPen(cp)
        for (cx, cy, dx, dy) in [(2,2,1,1),(w-2,2,-1,1),(2,h-2,1,-1),(w-2,h-2,-1,-1)]:
            p.drawLine(cx, cy, cx + dx*cl, cy)
            p.drawLine(cx, cy, cx, cy + dy*cl)

        # Pixel-style gold JARVIS logo
        self._paint_pixel_logo(p)
        # Gold particles
        self._paint_particles(p)
        p.end()

    def _paint_pixel_logo(self, p: QPainter):
        """Draw pixel-block JARVIS letters in layered gold."""
        word    = "JARVIS"
        px_size = 3          # size of each pixel block
        gap     = 2          # gap between letters
        letter_w= 6 * px_size + gap   # 6 cols per letter + gap
        total_w = len(word) * letter_w
        start_x = 32
        base_y  = 22 - (9 * px_size) // 2    # vertically centred in 28px header

        for li, ch in enumerate(word):
            pixels = _PIXEL_FONT.get(ch, [])
            ox = start_x + li * letter_w

            # Shadow pass
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(QColor(80, 50, 0, 120)))
            for (px, py) in pixels:
                p.drawRect(ox + px * px_size + 1, base_y + py * px_size + 1, px_size, px_size)

            # Outer glow
            p.setBrush(QBrush(QColor(212, 175, 55, 35)))
            for (px, py) in pixels:
                p.drawRect(ox + px * px_size - 1, base_y + py * px_size - 1,
                           px_size + 2, px_size + 2)

            # Main gold gradient per pixel row
            for (px, py) in pixels:
                t = py / 8.0
                r = int(C_GOLD3.red()   + t * (C_GOLD2.red()   - C_GOLD3.red()))
                g = int(C_GOLD3.green() + t * (C_GOLD2.green() - C_GOLD3.green()))
                b = int(C_GOLD3.blue()  + t * (C_GOLD2.blue()  - C_GOLD3.blue()))
                # Invert: bright top, dark bottom
                r2 = int(C_GOLD2.red()   + t * (C_GOLD3.red()   - C_GOLD2.red()))
                g2 = int(C_GOLD2.green() + t * (C_GOLD3.green() - C_GOLD2.green()))
                b2 = int(C_GOLD2.blue()  + t * (C_GOLD3.blue()  - C_GOLD2.blue()))
                p.setBrush(QBrush(QColor(r2, g2, b2)))
                p.drawRect(ox + px * px_size, base_y + py * px_size, px_size, px_size)

            # Specular top-edge highlight
            p.setBrush(QBrush(QColor(255, 240, 160, 200)))
            for (px, py) in pixels:
                if py == 0:
                    p.drawRect(ox + px * px_size, base_y + py * px_size, px_size, 1)

    def _paint_particles(self, p: QPainter):
        p.setPen(Qt.PenStyle.NoPen)
        for pt in self._particles:
            a = int(pt.life * 190)
            if a < 5: continue
            clr = C_GOLD if pt.gold else C_BLUE
            glow = QRadialGradient(pt.x, pt.y, pt.size * 2.8)
            glow.setColorAt(0.0, QColor(clr.red(), clr.green(), clr.blue(), a))
            glow.setColorAt(1.0, QColor(clr.red(), clr.green(), clr.blue(), 0))
            p.setBrush(QBrush(glow))
            s = pt.size * 2.8
            p.drawEllipse(QPointF(pt.x, pt.y), s, s)

    # â”€â”€ Confirmation flow â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    @pyqtSlot(str)
    def _on_confirm_request(self, question: str):
        self._confirm_lbl.setText(question[:80] + ("â€¦" if len(question) > 80 else ""))
        self._confirm_bar.setVisible(True)
        self._scroll_bottom()

    def _confirm_answer(self, yes: bool):
        self._confirm_bar.setVisible(False)
        self.signals.confirm_response.emit(yes)

    # â”€â”€ Ask user for missing info â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    @pyqtSlot(str)
    def _on_ask_user(self, prompt: str):
        self._add_bubble(prompt, "assistant")
        self._input.setPlaceholderText(prompt[:50] + "â€¦" if len(prompt) > 50 else prompt)
        self._input.setFocus()

    # â”€â”€ Voice input â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    def _start_voice(self):
        if self._processing: return
        self._voice_btn.setStyleSheet(f"color:{C_BLUE.name()}; font-size:13px;")
        self._apply_state("listening")
        import threading
        def _capture():
            try:
                import speech_recognition as sr
                recognizer = sr.Recognizer()
                with sr.Microphone() as source:
                    recognizer.adjust_for_ambient_noise(source, duration=0.3)
                    audio = recognizer.listen(source, timeout=6, phrase_time_limit=8)
                text = recognizer.recognize_google(audio)
                self.signals.voice_text.emit(text)
            except ImportError:
                self.signals.error_occurred.emit(
                    "SpeechRecognition not installed. Run: pip install SpeechRecognition pyaudio")
            except Exception as e:
                self.signals.error_occurred.emit(f"Voice error: {e}")
            finally:
                # Reset button on main thread
                from PyQt6.QtCore import QTimer
                QTimer.singleShot(0, self._reset_voice_btn)
        threading.Thread(target=_capture, daemon=True).start()

    def _reset_voice_btn(self):
        self._voice_btn.setStyleSheet(f"color:{C_SUB.name()}; font-size:13px;")
        if not self._processing:
            self._apply_state("ready")

    @pyqtSlot(str)
    def _on_voice_text(self, text: str):
        self._input.setText(text)
        self._submit()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape: self._hide()
        else: super().keyPressEvent(event)

