"""Qt6 (PySide6) — theme QSS, models và widgets cho GEV Console.

Không import snapshot/pypylon ở đây (chỉ GUI thuần).
"""

import time
from html import escape
from string import Template

import numpy as np
from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (QComboBox, QHBoxLayout, QLabel,
                               QPlainTextEdit, QPushButton, QSizePolicy,
                               QVBoxLayout, QWidget)

# --------------------------------------------------------------- colors
# "Soft dark": nền slate thay vì đen thuần, hợp dùng dưới đèn sáng
BG       = "#171e28"
PANEL    = "#1e2735"
PANEL2   = "#263246"
PANEL3   = "#2f3d54"
FIELD    = "#121924"
BORDER   = "#2c3a52"
BORDER2  = "#3d4f6d"
TEXT     = "#e2eaf5"
MUTED    = "#94a5bd"
MUTED2   = "#7b8ca4"
ACCENT   = "#4cc9e8"
ACCENT_H = "#2eb4d4"
GREEN    = "#4ac162"
AMBER    = "#e6b84d"
RED      = "#ef5a52"
TEAL     = "#1fc8b4"
ALT      = "#222d3e"    # row xen kẽ bảng
HOVER    = "#374863"
PRESSED  = "#141b25"
ACCENT_D = "#1d3a45"    # accent khi disabled

# ---------------------------------------------------------------- QSS
QSS = Template("""
QWidget { background: $BG; color: $TEXT;
          font-family: "Segoe UI"; font-size: 10pt; }
QMainWindow::separator { background: $BORDER; width: 3px; height: 3px; }
QToolBar { background: $PANEL; border-bottom: 1px solid $BORDER;
           padding: 5px; spacing: 8px; }
QToolBar::separator { background: $BORDER; width: 1px; margin: 4px 6px; }
QToolButton { background: $PANEL3; color: $ACCENT; border: 1px solid $BORDER2;
              padding: 6px 14px; font-weight: bold; }
QToolButton:hover { background: $HOVER; }
QToolButton:pressed { background: $PRESSED; }
QToolButton:disabled { color: $MUTED2; background: $PANEL2; }
QMenuBar { background: $PANEL; border-bottom: 1px solid $BORDER; }
QMenuBar::item { padding: 5px 12px; background: transparent; }
QMenuBar::item:selected { background: $PANEL3; color: $ACCENT; }
QMenu { background: $PANEL; border: 1px solid $BORDER; }
QMenu::item { padding: 6px 24px; }
QMenu::item:selected { background: $PANEL3; color: $ACCENT; }
QSplitter::handle { background: $BORDER; width: 2px; }
QTabWidget::pane { border: 1px solid $BORDER; background: $PANEL;
                   top: -1px; }
QTabBar::tab { background: $PANEL; color: $MUTED; padding: 8px 20px;
               font-weight: bold; border: 1px solid $PANEL; }
QTabBar::tab:hover { color: $TEXT; }
QTabBar::tab:selected { color: $ACCENT; background: $PANEL2;
                        border-bottom: 2px solid $ACCENT; }
QGroupBox { border: 1px solid $BORDER; margin-top: 12px; padding: 8px;
            font-weight: bold; color: $MUTED; font-size: 9pt; }
QGroupBox::title { subcontrol-origin: margin; left: 8px; padding: 0 4px; }
QTreeView, QTableView { background: $PANEL; alternate-background-color: $ALT;
    border: 1px solid $BORDER; gridline-color: $BORDER;
    font-family: "Consolas"; font-size: 9pt; }
QTreeView::item, QTableView::item { padding: 4px 0px; }
QTreeView::item:selected, QTableView::item:selected {
    background: $PANEL3; color: $ACCENT; }
QHeaderView::section { background: $PANEL2; color: $MUTED;
    border: 1px solid $BORDER; border-right: 1px solid $BORDER;
    padding: 4px 6px; font-weight: bold; font-family: "Consolas"; }
QLineEdit { background: $PANEL2; border: 1px solid $BORDER; padding: 6px;
            font-family: "Consolas"; color: $TEXT;
            selection-background-color: $ACCENT;
            selection-color: $BG; }
QLineEdit:focus { border: 1px solid $ACCENT; }
QLineEdit[invalid="true"] { border: 1px solid $RED; }
QPushButton { background: $PANEL2; border: 1px solid $BORDER;
              color: $TEXT; padding: 8px 10px; font-weight: bold; }
QPushButton:hover { background: $PANEL3; border-color: $BORDER2; }
QPushButton:pressed { background: $PRESSED; }
QPushButton:disabled { color: $MUTED2; }
QPushButton[accent="true"] { background: $ACCENT; color: #0d141d;
                             border: none; }
QPushButton[accent="true"]:hover { background: $ACCENT_H; }
QPushButton[accent="true"]:disabled { background: $ACCENT_D;
                                      color: $MUTED2; }
QCheckBox { color: $MUTED; spacing: 8px; }
QCheckBox::indicator { width: 14px; height: 14px; border: 1px solid $BORDER2;
                       background: $PANEL2; }
QCheckBox::indicator:checked { border-color: $ACCENT;
                               background: $ACCENT; }
QComboBox { background: $PANEL2; border: 1px solid $BORDER;
            padding: 3px 8px; font-size: 9pt; }
QComboBox QAbstractItemView { background: $PANEL2; color: $TEXT;
    border: 1px solid $BORDER2; selection-background-color: $PANEL3;
    selection-color: $ACCENT; }
QPlainTextEdit { background: $PANEL; color: $TEXT;
    border: 1px solid $BORDER; font-family: "Consolas"; font-size: 9pt; }
QStatusBar { background: $PANEL2; border-top: 1px solid $BORDER; }
QStatusBar::item { border: none; }
QScrollBar:vertical { background: $PANEL; width: 10px; margin: 0; }
QScrollBar::handle:vertical { background: $BORDER2; min-height: 24px; }
QScrollBar::handle:vertical:hover { background: $HOVER; }
QScrollBar:horizontal { background: $PANEL; height: 10px; margin: 0; }
QScrollBar::handle:horizontal { background: $BORDER2; min-width: 24px; }
QScrollBar::add-line, QScrollBar::sub-line { height: 0; width: 0; }
QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }
QToolTip { background: $PANEL2; color: $TEXT; border: 1px solid $ACCENT; }
QMessageBox QLabel { color: $TEXT; }
""").substitute(BG=BG, PANEL=PANEL, PANEL2=PANEL2, PANEL3=PANEL3,
                FIELD=FIELD, BORDER=BORDER, BORDER2=BORDER2, TEXT=TEXT,
                MUTED=MUTED, MUTED2=MUTED2, ACCENT=ACCENT,
                ACCENT_H=ACCENT_H, ACCENT_D=ACCENT_D, ALT=ALT,
                HOVER=HOVER, PRESSED=PRESSED, RED=RED)


# --------------------------------------------------------------- models


class DeviceTableModel(QAbstractTableModel):
    """Danh sách camera: LED · MODEL · S/N · IP · MAC."""

    COLS = ("●", "MODEL", "S/N", "IP", "MAC")

    def __init__(self, parent=None):
        super().__init__(parent)
        self._cams = []

    def set_devices(self, cams):
        self.beginResetModel()
        self._cams = list(cams)
        self.endResetModel()

    def cam_at(self, row):
        return self._cams[row] if 0 <= row < len(self._cams) else None

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self._cams)

    def columnCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.COLS)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        cam = self._cams[index.row()]
        col = index.column()
        if role == Qt.ItemDataRole.DisplayRole:
            if col == 0:
                return "●"          # đèn link — camera đang sống
            key = ("model", "serial", "ip", "mac")[col - 1]
            return cam.get(key) or "—"
        if role == Qt.ItemDataRole.ForegroundRole and col == 0:
            return QColor(GREEN)
        return None

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if role == Qt.ItemDataRole.DisplayRole:
            if orientation == Qt.Orientation.Horizontal:
                return self.COLS[section]
            return None
        return None


class RegisterTableModel(QAbstractTableModel):
    """Bootstrap registers: ADDR · NAME · RAW · DECODED.

    status: 'ok' | 'write' (vừa ghi — highlight cyan + nền) | 'err'."""

    COLS = ("ADDR", "NAME", "RAW", "DECODED")

    def __init__(self, parent=None):
        super().__init__(parent)
        self._rows = []

    def set_rows(self, rows):
        self.beginResetModel()
        self._rows = list(rows)
        self.endResetModel()

    def addr_at(self, row):
        return self._rows[row][0]

    def decoded_at(self, row):
        return self._rows[row][3]

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self._rows)

    def columnCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.COLS)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        addr, name, raw, dec, status = self._rows[index.row()]
        col = index.column()
        if role == Qt.ItemDataRole.DisplayRole:
            return (f"0x{addr:08X}" if addr is not None else "—",
                    name, "—" if raw is None else f"0x{raw:08X}", dec)[col]
        if role == Qt.ItemDataRole.ForegroundRole:
            if col == 0:
                return QColor(MUTED)
            if status == "write":
                return QColor(ACCENT)
            if status == "err":
                return QColor(RED)
            return None
        if role == Qt.ItemDataRole.BackgroundRole and status == "write":
            c = QColor(ACCENT)
            c.setAlpha(28)
            return c
        return None

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if role == Qt.ItemDataRole.DisplayRole:
            if orientation == Qt.Orientation.Horizontal:
                return self.COLS[section]
            return str(section)
        return None


# --------------------------------------------------------------- widgets


class ImageView(QWidget):
    """Khung xem frame: ảnh scale giữ tỉ lệ + crosshair tâm + overlay meta.

    Vẽ bằng QPainter trong paintEvent (mượt hơn nhiều Label+Pixmap của Tk).
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._base = None       # QPixmap gốc
        self._scaled = None     # QPixmap đã scale theo widget
        self._meta = None
        self._msg = "— NO FRAME —\nGRAB hoặc LIVE để xem"
        self.setMinimumSize(360, 260)
        self.setSizePolicy(QSizePolicy.Policy.Expanding,
                           QSizePolicy.Policy.Expanding)

    def set_frame(self, pix: QPixmap, meta=None):
        self._base, self._meta = pix, meta
        self._msg = None
        self._rescale()
        self.update()

    def set_placeholder(self, msg="— NO FRAME —"):
        self._base = self._scaled = None
        self._msg = msg
        self.update()

    def resizeEvent(self, ev):
        self._rescale()

    def _rescale(self):
        if self._base is None or self._base.isNull():
            self._scaled = None
            return
        self._scaled = self._base.scaled(
            self.size(), Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation)

    def paintEvent(self, ev):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(FIELD))
        if self._scaled is None:
            p.setPen(QColor(MUTED2))
            p.setFont(QFont("Segoe UI", 10))
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter,
                       self._msg or "")
            p.end()
            return
        w, h = self._scaled.width(), self._scaled.height()
        x, y = (self.width() - w) // 2, (self.height() - h) // 2
        p.drawPixmap(x, y, self._scaled)
        p.setPen(QPen(QColor(BORDER2), 1))
        p.drawRect(x - 1, y - 1, w + 2, h + 2)
        cx, cy = self.width() // 2, self.height() // 2
        p.setPen(QPen(QColor(GREEN), 1))
        p.drawLine(cx - 14, cy, cx + 14, cy)
        p.drawLine(cx, cy - 14, cx, cy + 14)
        if self._meta:
            p.setFont(QFont("Consolas", 9))
            p.setPen(QColor(GREEN))
            p.drawText(x + 6, y + 16,
                       f"{self._meta.get('w', '?')}x{self._meta.get('h', '?')}"
                       f"  {self._meta.get('fmt', '')}")
        p.end()


class HistogramWidget(QWidget):
    """Histogram 32 bin — tối = xanh lá, giữa = vàng, bão hòa = đỏ."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._hist = None
        self.setFixedHeight(72)

    def update_from_array(self, arr):
        flat = arr[..., 0] if arr.ndim == 3 else arr
        hist, _ = np.histogram(flat.ravel(), bins=32, range=(0, 256))
        self._hist = hist
        self.update()

    def clear(self):
        self._hist = None
        self.update()

    def paintEvent(self, ev):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(FIELD))
        base = self.height() - 2
        p.setPen(QPen(QColor(BORDER2)))
        p.drawLine(2, base, self.width() - 2, base)
        if self._hist is not None:
            peak = max(int(self._hist.max()), 1)
            n = len(self._hist)
            bw = max(1, (self.width() - 4) // n)
            for i, v in enumerate(self._hist):
                bh = int((self.height() - 12) * int(v) / peak)
                col = GREEN if i < 16 else (AMBER if i < 26 else RED)
                p.fillRect(2 + int(i * bw), base - bh, int(bw) - 1, bh,
                           QColor(col))
        p.end()


class ConsolePane(QWidget):
    """Log kỹ thuật: [HH:MM:SS.mmm] [LEVEL] msg + filter + clear."""

    COLORS = {"info": ACCENT, "ok": GREEN, "warn": AMBER, "err": RED,
              "muted": MUTED2}
    LABELS = {"info": "INFO", "ok": " OK ", "warn": "WARN", "err": "FAIL",
              "muted": "DBUG"}

    def __init__(self, parent=None):
        super().__init__(parent)
        self._hist = []
        self._filter = "ALL"
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)

        head = QHBoxLayout()
        title = QLabel("C O N S O L E")
        title.setStyleSheet(f"color:{MUTED}; font-weight:bold; font-size:8pt;")
        self._count = QLabel("")
        self._count.setStyleSheet(
            f"color:{MUTED2}; font-family:Consolas; font-size:8pt;")
        self.filt = QComboBox()
        self.filt.addItems(["ALL", "WARN", "FAIL"])
        self.filt.setFixedWidth(90)
        self.filt.currentTextChanged.connect(self._set_filter)
        clr = QPushButton("CLEAR")
        clr.setStyleSheet(f"color:{MUTED2}; border:none; background:transparent;"
                          f" font-size:8pt; font-weight:bold;")
        clr.clicked.connect(self.clear)
        head.addWidget(title)
        head.addWidget(self._count)
        head.addStretch(1)
        head.addWidget(self.filt)
        head.addWidget(clr)
        lay.addLayout(head)

        self.edit = QPlainTextEdit()
        self.edit.setReadOnly(True)
        self.edit.setMaximumBlockCount(5000)
        lay.addWidget(self.edit)
        self.setMinimumHeight(150)

    # -- API --

    def log(self, msg, tag="muted"):
        tag = tag if tag in self.COLORS else "muted"
        ts = time.strftime("%H:%M:%S") + ".%03d" % (int(time.time() * 1000) % 1000)
        line = (ts, tag, str(msg))
        self._hist.append(line)
        self._count.setText(f"{len(self._hist)} dòng")
        if self._match(tag):
            self._line(*line)

    def clear(self):
        self._hist = []
        self.edit.clear()
        self._count.setText("")

    # -- internal --

    def _match(self, tag):
        if self._filter == "ALL":
            return True
        if self._filter == "WARN":
            return tag in ("warn", "err")
        return tag == "err"

    def _line(self, ts, tag, msg):
        c = self.COLORS[tag]
        self.edit.appendHtml(
            f'<span style="color:{MUTED2}">[{ts}]</span> '
            f'<span style="color:{c}">[{self.LABELS[tag]}]</span> '
            f'{escape(msg)}')

    def _set_filter(self, txt):
        self._filter = txt
        self.edit.clear()
        for ts, tag, msg in self._hist:
            if self._match(tag):
                self._line(ts, tag, msg)
