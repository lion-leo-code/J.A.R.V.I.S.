"""
JARVIS HUD Overlay — v4
Cyber blue (#00E5FF) primary palette. Holographic corner panels with telemetry
bars, live data, mini radar, and animated scan lines.
Click-through full-screen overlay — never intercepts mouse events.
"""
import os
from PyQt6.QtGui import QGuiApplication, QPolygon, QConicalGradient
from PyQt6.QtCore import QPoint

os.environ["QT_AUTO_SCREEN_SCALE_FACTOR"] = "1"

import math
from PyQt6.QtWidgets import QWidget, QApplication
from PyQt6.QtCore    import Qt, QTimer, QRect, QRectF, pyqtSlot
from PyQt6.QtGui     import (
    QPainter, QColor, QFont, QPen, QBrush,
    QLinearGradient, QRadialGradient, QPainterPath
)

# ── Palette ───────────────────────────────────────────────────────────────────
BLUE        = QColor(  0, 229, 255)     # #00E5FF  primary
BLUE_DIM    = QColor(  0, 180, 210, 160)
BLUE_GLOW   = QColor(  0, 229, 255,  28)
GREEN       = QColor(  0, 255,  65)     # #00FF41  secondary
GOLD        = QColor(212, 175,  55)     # accent
AMBER       = QColor(255, 200,   0)     # warning
RED_ALT     = QColor(255,  60,  60)     # critical
TINT        = QColor(  0,  10,  25,  65)   # full-screen overlay
SCAN_CLR    = QColor(  0, 229, 255,  12)
LABEL_CLR   = QColor(  0, 160, 200, 170)
VALUE_CLR   = QColor(  0, 229, 255, 235)
BG_PANEL    = QColor(  0,  14,  26, 185)   # panel glass
BORDER_CLR  = QColor(  0, 229, 255,  70)


def _font(size: int, bold: bool = False) -> QFont:
    f = QFont("Courier New", size)
    f.setStyleHint(QFont.StyleHint.Monospace)
    f.setWeight(QFont.Weight.Bold if bold else QFont.Weight.Normal)
    return f


def _val_color(pct: float) -> QColor:
    if pct < 70: return BLUE
    if pct < 88: return AMBER
    return RED_ALT


class HudOverlay(QWidget):
    """Full-screen click-through HUD overlay."""

    PANEL_W = 265
    PANEL_H = 175
    MARGIN  = 20
    LINE_H  = 21
    BRACKET = 36
    BR_T    = 3.0

    def __init__(self, parent=None):
        super().__init__(parent)
        self._stats: dict = {}
        self._phase   = 0.0
        self._scan_y  = 0.0
        self._rot     = 0.0
        self._radar_dots: list = []   # list of (angle, dist, age) for radar blips
        self._visible = False

        self._setup_window()

        self._anim = QTimer(self)
        self._anim.timeout.connect(self._tick)
        self._anim.setInterval(40)  # 25 fps

        # Spawn radar blips
        self._blip_timer = QTimer(self)
        self._blip_timer.timeout.connect(self._spawn_blip)
        self._blip_timer.setInterval(1800)

    def _setup_window(self):
        screen = QApplication.primaryScreen()
        geo    = screen.geometry() if screen else QRect(0, 0, 1920, 1080)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint    |
            Qt.WindowType.WindowStaysOnTopHint   |
            Qt.WindowType.Tool                   |
            Qt.WindowType.WindowTransparentForInput
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setGeometry(geo)

    # ── Public API ────────────────────────────────────────────────────────────
    @pyqtSlot()
    def show_hud(self):
        if self._visible: return
        self._visible = True
        self.show(); self.raise_()
        self._anim.start()
        self._blip_timer.start()

    @pyqtSlot()
    def hide_hud(self):
        if not self._visible: return
        self._visible = False
        self._anim.stop()
        self._blip_timer.stop()
        self.hide()

    @pyqtSlot(dict)
    def update_stats(self, stats: dict):
        self._stats = stats
        if self._visible: self.update()

    # ── Animation ─────────────────────────────────────────────────────────────
    def _tick(self):
        self._phase  = (self._phase + 0.035) % (2 * math.pi)
        self._scan_y = (self._scan_y + 1.6) % max(1, self.height())
        self._rot    = (self._rot + 0.5) % 360
        # Age radar blips
        self._radar_dots = [(a, d, age + 1) for a, d, age in self._radar_dots if age < 80]
        self.update()

    def _spawn_blip(self):
        import random
        self._radar_dots.append((random.uniform(0, 360), random.uniform(0.2, 0.9), 0))

    # ── Paint ─────────────────────────────────────────────────────────────────
    def paintEvent(self, _event):
        if not self._visible: return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        W, H = self.width(), self.height()

        p.fillRect(0, 0, W, H, TINT) # Overlay tint

        # Surgical Fix: Calling the specific Elite-style corner methods
        self._draw_top_left(p)        # EKG Heartbeat
        self._draw_tr_panel(p, W - self.PANEL_W - 20, 20) # Comms
        self._draw_bottom_left(p)     # Tactical Radar
        self._draw_bottom_right(p)    # Music Visualizer

        p.end()

    # ── Screen corner brackets ────────────────────────────────────────────────
    def _draw_screen_brackets(self, p: QPainter, W: int, H: int):
        glow_a = int(140 + 60 * math.sin(self._phase))
        arm    = self.BRACKET
        off    = 6

        # Glow pass
        gpen = QPen(QColor(0, 229, 255, glow_a // 5), self.BR_T * 3.5)
        gpen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(gpen)
        for (x, y, hx, hy) in [(off,off,arm,arm),(W-off,off,-arm,arm),
                                 (off,H-off,arm,-arm),(W-off,H-off,-arm,-arm)]:
            p.drawLine(x,y,x+hx,y); p.drawLine(x,y,x,y+hy)

        # Sharp pass
        pen = QPen(QColor(0, 229, 255, glow_a), self.BR_T)
        pen.setCapStyle(Qt.PenCapStyle.SquareCap)
        p.setPen(pen)
        for (x, y, hx, hy) in [(off,off,arm,arm),(W-off,off,-arm,arm),
                                 (off,H-off,arm,-arm),(W-off,H-off,-arm,-arm)]:
            p.drawLine(x,y,x+hx,y); p.drawLine(x,y,x,y+hy)

    # ── Panel glass background ────────────────────────────────────────────────
    def _panel_bg(self, p: QPainter, x: int, y: int, corner: str):
        pw, ph, r = self.PANEL_W, self.PANEL_H, 6

        # Panel gradient — edge toward screen edge is lighter
        pg = QLinearGradient(x, y, x + pw, y + ph)
        if corner in ("TL","BL"):
            pg.setColorAt(0.0, QColor(0, 40, 70, 200))
            pg.setColorAt(1.0, QColor(0, 14, 26, 160))
        else:
            pg.setColorAt(0.0, QColor(0, 14, 26, 160))
            pg.setColorAt(1.0, QColor(0, 40, 70, 200))

        p.setBrush(QBrush(pg)); p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(x, y, pw, ph, r, r)

        # Border glow
        ba = int(55 + 30 * math.sin(self._phase))
        p.setPen(QPen(QColor(0, 229, 255, ba), 1.0))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(x, y, pw, ph, r, r)

        # Inner corner accent ticks
        tick = 10
        tp   = QPen(BLUE, 1.8)
        p.setPen(tp)
        if corner == "TL":
            p.drawLine(x, y, x+tick, y); p.drawLine(x, y, x, y+tick)
        elif corner == "TR":
            p.drawLine(x+pw, y, x+pw-tick, y); p.drawLine(x+pw, y, x+pw, y+tick)
        elif corner == "BL":
            p.drawLine(x, y+ph, x+tick, y+ph); p.drawLine(x, y+ph, x, y+ph-tick)
        elif corner == "BR":
            p.drawLine(x+pw, y+ph, x+pw-tick, y+ph); p.drawLine(x+pw, y+ph, x+pw, y+ph-tick)

    # ── Text helpers ──────────────────────────────────────────────────────────
    def _label(self, p, x, y, text):
        p.setFont(_font(8)); p.setPen(QPen(LABEL_CLR))
        p.drawText(x, y, text)

    def _value(self, p, x, y, text, clr=None):
        p.setFont(_font(10, bold=True))
        p.setPen(QPen(clr or VALUE_CLR))
        p.drawText(x, y, text)

    def _value_r(self, p, rx, y, text, clr=None, width=220):
        """Right-aligned value."""
        p.setFont(_font(10, bold=True))
        p.setPen(QPen(clr or VALUE_CLR))
        p.drawText(rx - width, y, width, 16, Qt.AlignmentFlag.AlignRight, text)

    def _section(self, p, x, y, text, right=False):
        p.setFont(_font(7)); p.setPen(QPen(QColor(0, 150, 190, 130)))
        if right:
            p.drawText(x - 230, y, 230, 12, Qt.AlignmentFlag.AlignRight, f"── {text} ──")
        else:
            p.drawText(x, y, f"── {text} ──")

    def _bar(self, p, x, y, w, pct, right=False):
        """Horizontal progress bar with glow."""
        h  = 4
        bx = x if not right else x - w
        # Track
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(QColor(0, 50, 80)))
        p.drawRoundedRect(bx, y, w, h, 2, 2)
        # Fill
        fill = int(w * max(0, min(1, pct / 100)))
        if fill > 0:
            fc = _val_color(pct)
            # Glow under fill
            gfill = QLinearGradient(bx, y, bx + fill, y)
            gfill.setColorAt(0.0, QColor(fc.red(), fc.green(), fc.blue(), 80))
            gfill.setColorAt(1.0, QColor(fc.red(), fc.green(), fc.blue(), 220))
            p.setBrush(QBrush(gfill))
            p.drawRoundedRect(bx, y, fill, h, 2, 2)

    # ── TOP LEFT — Power + CPU ────────────────────────────────────────────────
    def _draw_top_left(self, p: QPainter):
        p.setPen(QPen(BLUE, 1))
        p.drawLine(50, 50, 250, 50)
        p.drawLine(50, 50, 50, 150)
        
        p.setFont(QFont("Orbitron", 10, QFont.Weight.Bold))
        p.drawText(60, 75, "VITALS // BIOMETRIC_SCAN")
        
        # Pulsing EKG Path
        path = QPainterPath()
        path.moveTo(60, 120)
        for i in range(45):
            x = 60 + (i * 4)
            y = 120
            # Heartbeat spike logic tied to the animation phase
            pulse_pos = (self._phase * 4) % 10
            if 2.0 < pulse_pos < 2.8:
                diff = pulse_pos - 2.0
                y -= math.sin(diff * 12) * 35 if diff < 0.4 else -math.sin(diff * 6) * 12
            path.lineTo(x, y)
        
        p.setPen(QPen(BLUE, 1.5))
        p.drawPath(path)

    # ── TOP RIGHT — Network ───────────────────────────────────────────────────
    def _draw_tr_panel(self, p, x, y):
        w = self.width()
        # Angled Polygon Panel
        poly = QPolygon([
            QPoint(w - 300, 50),
            QPoint(w - 50, 50),
            QPoint(w - 75, 100),
            QPoint(w - 300, 100)
        ])
        p.setBrush(QBrush(QColor(0, 229, 255, 15)))
        p.setPen(QPen(BLUE, 1))
        p.drawPolygon(poly)
        
        p.setPen(QPen(BLUE, 1))
        p.drawText(w - 280, 85, "COMMUNICATION // CH-09")
        
        # Status LED (Blinking Amber)
        status_color = AMBER if math.sin(self._phase * 5) > 0 else BLUE_DIM
        p.setBrush(QBrush(status_color))
        p.drawEllipse(w - 280, 115, 10, 10)
        p.drawText(w - 260, 125, "ENCRYPTION_ACTIVE")

    # ── BOTTOM LEFT — Memory + radar ─────────────────────────────────────────
    def _draw_bottom_left(self, p: QPainter):
        cx, cy = 150, self.height() - 150
        radius = 100
        
        # Radar Rings
        p.setPen(QPen(BLUE_DIM, 0.8))
        p.drawEllipse(cx - radius, cy - radius, radius * 2, radius * 2)
        
        # The "Elite" Tactical Sweep
        angle = (self._phase * 120) % 360
        grad = QConicalGradient(cx, cy, -angle)
        grad.setColorAt(0, QColor(0, 229, 255, 180))
        grad.setColorAt(0.2, QColor(0, 229, 255, 0))
        
        p.setBrush(QBrush(grad))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawPie(cx - radius, cy - radius, radius * 2, radius * 2, int(angle * 16), 45 * 16)
        
        p.setPen(QPen(BLUE, 1))
        p.drawText(cx - 40, cy + radius + 30, "TACTICAL_RADAR")

    # ── BOTTOM RIGHT — Devices ────────────────────────────────────────────────
    def _draw_bottom_right(self, p: QPainter):
        w, h = self.width(), self.height()
        x_start = w - 280
        y_base = h - 80
        
        p.setPen(QPen(BLUE, 1))
        p.drawText(x_start, h - 50, "AUDIO_SENSORS // FEED_ACTIVE")
        
        for i in range(15):
            # Simulated frequency bars
            val = abs(math.sin(self._phase * 3.5 + i)) * 70
            # Color shift to Gold for peak volumes
            bar_color = GOLD if val > 60 else BLUE
            p.setBrush(QBrush(bar_color))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawRect(x_start + (i * 18), int(y_base - val), 12, int(val))

    # ── Sparkline ─────────────────────────────────────────────────────────────
    _cpu_history: list = []

    def _draw_sparkline(self, p, x, y, w, h, current_val):
        HudOverlay._cpu_history.append(current_val)
        if len(HudOverlay._cpu_history) > 30:
            HudOverlay._cpu_history = HudOverlay._cpu_history[-30:]

        hist = HudOverlay._cpu_history
        if len(hist) < 2: return

        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(QColor(0, 40, 70, 100)))
        p.drawRoundedRect(x, y, w, h, 2, 2)

        step = w / (len(hist) - 1)
        pts  = [(x + i * step, y + h - (v / 100) * h) for i, v in enumerate(hist)]

        path = QPainterPath()
        path.moveTo(pts[0][0], pts[0][1])
        for (px, py) in pts[1:]:
            path.lineTo(px, py)

        pen = QPen(BLUE, 1.2)
        p.setPen(pen); p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(path)

from PyQt6.QtCore import QRectF
