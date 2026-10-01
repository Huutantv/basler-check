"""GEV Console — bản Qt6 (PySide6) cho công cụ camera GigE Vision.

Chạy:  python gui_qt.py
Yêu cầu: pip install PySide6 numpy   (pypylon cho tab IMAGE)

Bản gui.py (Tkinter) vẫn còn làm fallback khi máy chưa cài Qt.
Logic nghiệp vụ dùng nguyên gigetools.py / snapshot.py.
"""

import base64
import os
import sys
import time

from PySide6.QtCore import (QObject, QRegularExpression, Qt, QThread,
                            QTimer, Signal)
from PySide6.QtGui import (QFont, QIcon, QRegularExpressionValidator,
                           QShortcut)

from PySide6.QtWidgets import (QAbstractItemView, QApplication, QCheckBox,
                               QDockWidget, QFormLayout, QGroupBox,
                               QHBoxLayout, QHeaderView, QLabel, QLineEdit,
                               QMainWindow, QMessageBox, QPushButton,
                               QSplitter, QStatusBar, QTableView,
                               QTabWidget, QToolBar, QVBoxLayout, QWidget)

import gigetools as gt
from qt_widgets import (ACCENT, AMBER, GREEN, MUTED, MUTED2, QSS, RED, TEAL,
                        ConsolePane, DeviceTableModel, HistogramWidget,
                        ImageView, RegisterTableModel)

APP_NAME    = "GEV Console"
APP_VERSION = "1.0.0"
VENDOR      = "Factory Automation"


def _resource(name):
    """Đường dẫn file nhúng — hoạt động cả khi chạy từ PyInstaller onefile."""
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, name)


IP_RE = QRegularExpression(r"^\d{0,3}(\.\d{0,3}){0,3}$")


class Worker(QThread):
    """Chạy 1 hàm nghiệp vụ ở thread nền; log/done/fail qua signal an toàn."""

    log = Signal(str, str)
    done = Signal(str, object)
    fail = Signal(str)

    def __init__(self, fn, done_label, parent=None):
        super().__init__(parent)
        self.fn, self.done_label = fn, done_label

    def run(self):
        try:
            result = self.fn(self.log.emit)
            self.done.emit(self.done_label, result)
        except gt.GVCPError as e:
            self.fail.emit(str(e))
        except Exception as e:  # noqa: BLE001
            self.fail.emit(f"{type(e).__name__}: {e}")


class LiveBridge(QObject):
    """Cầu nối LiveSession (thread raw của snapshot.py) → GUI qua signal."""

    frame = Signal(str, object)   # preview_b64, meta
    ended = Signal(object)

    def __init__(self):
        super().__init__()
        self.session = None

    def start(self, serial):
        import snapshot
        self.session = snapshot.LiveSession(
            serial,
            frame_cb=lambda b64, meta: self.frame.emit(b64, meta),
            on_end=lambda err: self.ended.emit(err))
        self.session.start()

    def stop(self):
        if self.session:
            self.session.stop()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{APP_NAME.upper()} — GigE Vision · {VENDOR}")
        self.setWindowIcon(QIcon(_resource("app_icon.ico")))
        self.resize(1280, 860)
        self.cameras, self.selected, self.last_snap = [], None, None
        self.worker = None
        self.pending_regs = None
        self.live = LiveBridge()
        self.live.frame.connect(self._on_live_frame)
        self.live.ended.connect(self._on_live_end)
        self._busy = False
        self._last_frame_t = time.time()

        self._build_ui()
        self._connect()
        self.console.log("GEV Console (Qt6) sẵn sàng — F5 scan · Ctrl+↵ PWRITE",
                         "info")
        QTimer.singleShot(120, self.scan)

    # ------------------------------------------------------------------ UI

    def _build_ui(self):
        mb = self.menuBar()
        m_help = mb.addMenu("&Help")
        m_help.addAction("&About", self.show_about)
        m_help.addSeparator()
        m_help.addAction("&Keyboard shortcuts", self.show_shortcuts)

        tb = QToolBar("main")
        tb.setMovable(False)
        self.addToolBar(tb)
        self.btn_scan = QPushButton("SCAN  [F5]")
        tb.addWidget(self.btn_scan)
        tb.addSeparator()
        lbl = QLabel("  Basler GigE · GVCP · pylon")
        lbl.setStyleSheet(f"color:{MUTED2};")
        tb.addWidget(lbl)
        tb.addSeparator()
        self.btn_forceip = QPushButton("FORCEIP")
        tb.addWidget(self.btn_forceip)
        self.btn_perm = QPushButton("PWRITE — ĐẶT IP VĨNH VIỄN")
        self.btn_perm.setProperty("accent", True)
        tb.addWidget(self.btn_perm)

        split = QSplitter(Qt.Orientation.Horizontal)

        # ---- cột trái: device list + NIC
        left = QWidget()
        lv = QVBoxLayout(left)
        lv.setContentsMargins(0, 0, 0, 0)
        lv.setSpacing(8)

        gb = QGroupBox("DEVICE LIST")
        gv = QVBoxLayout(gb)
        self.dev_model = DeviceTableModel()
        self.dev_view = QTableView()
        self.dev_view.setModel(self.dev_model)
        self.dev_view.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows)
        self.dev_view.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection)
        self.dev_view.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers)
        self.dev_view.setAlternatingRowColors(True)
        self.dev_view.setShowGrid(False)
        self.dev_view.verticalHeader().setVisible(False)
        hh = self.dev_view.horizontalHeader()
        hh.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        hh.setStretchLastSection(True)
        self.dev_view.setMinimumWidth(330)
        gv.addWidget(self.dev_view)
        lv.addWidget(gb, 3)

        nics = gt.get_local_interfaces() or []
        gb2 = QGroupBox("NETWORK INTERFACES")
        g2 = QVBoxLayout(gb2)
        lab = QLabel("\n".join(f"IPv4  {ip:<15} / {mask}"
                               for ip, mask, _ in nics)
                     or "(không có card mạng IPv4)")
        lab.setStyleSheet(f"color:{MUTED}; font-family:Consolas; font-size:9pt;")
        g2.addWidget(lab)
        lv.addWidget(gb2, 1)
        split.addWidget(left)

        # ---- giữa/phải: tabs
        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_device_tab(), "D E V I C E")
        self.tabs.addTab(self._build_image_tab(), "I M A G E")
        split.addWidget(self.tabs)
        split.setStretchFactor(0, 0)
        split.setStretchFactor(1, 1)
        split.setSizes([360, 900])
        self.setCentralWidget(split)

        # ---- console dock dưới
        self.console = ConsolePane()
        dock = QDockWidget("Console", self)
        dock.setAllowedAreas(Qt.DockWidgetArea.BottomDockWidgetArea)
        dock.setWidget(self.console)
        dock.setFeatures(QDockWidget.DockWidgetFeature.DockWidgetMovable)
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, dock)
        dock.setMinimumHeight(170)

        # ---- status bar chia ô
        sb = QStatusBar()
        self.setStatusBar(sb)
        self.st = {}
        for key in ("LINK", "CAMERA", "NET", "MODE"):
            k = QLabel(f"  {key}")
            k.setStyleSheet(f"color:{MUTED2}; font-size:8pt; font-weight:bold;")
            v = QLabel("—")
            v.setStyleSheet(f"color:{MUTED}; font-family:Consolas;")
            sb.addWidget(k)
            sb.addWidget(v)
            self.st[key] = v
        if nics:
            self.st["NET"].setText(f"{len(nics)} NIC")
            self.st["NET"].setStyleSheet(f"color:{GREEN}; font-family:Consolas;")
        self.st_right = QLabel("ready")
        self.st_right.setStyleSheet(f"color:{GREEN}; font-family:Consolas;")
        sb.addPermanentWidget(self.st_right)

    def _build_device_tab(self) -> QWidget:
        page = QWidget()
        h = QHBoxLayout(page)
        h.setContentsMargins(14, 14, 14, 14)

        col = QVBoxLayout()
        self.lbl_cam = QLabel("— NO DEVICE —")
        f = QFont("Segoe UI", 12)
        f.setBold(True)
        self.lbl_cam.setFont(f)
        col.addWidget(self.lbl_cam)
        self.lbl_detail = QLabel("SCAN để tìm camera (F5)")
        self.lbl_detail.setStyleSheet(
            f"color:{MUTED}; font-family:Consolas; font-size:9pt;")
        col.addWidget(self.lbl_detail)

        self.reg_model = RegisterTableModel()
        self.reg_view = QTableView()
        self.reg_view.setModel(self.reg_model)
        self.reg_view.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers)
        self.reg_view.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection)
        self.reg_view.verticalHeader().setVisible(False)
        rh = self.reg_view.horizontalHeader()
        rh.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        rh.setStretchLastSection(True)
        gb = QGroupBox("BOOTSTRAP REGISTERS  (GVCP READREG)")
        gvl = QVBoxLayout(gb)
        gvl.addWidget(self.reg_view)
        hint = QLabel("double-click dòng IP → điền vào form bên phải")
        hint.setStyleSheet(f"color:{MUTED2}; font-size:8pt;")
        gvl.addWidget(hint)
        col.addWidget(gb, 1)
        self.btn_regs = QPushButton("READ REGISTERS")
        col.addWidget(self.btn_regs)
        h.addLayout(col, 3)

        form_box = QGroupBox("IP TARGET")
        form_box.setMaximumWidth(360)
        fv = QVBoxLayout(form_box)
        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        self.e_ip = self._ip_edit("169.254.100.50")
        self.e_mask = self._ip_edit("255.255.0.0")
        self.e_gw = self._ip_edit("0.0.0.0")
        form.addRow("IP ADDRESS", self.e_ip)
        form.addRow("SUBNET MASK", self.e_mask)
        form.addRow("GATEWAY", self.e_gw)
        fv.addLayout(form)
        tip = QLabel("must match NIC subnet")
        tip.setStyleSheet(f"color:{MUTED2}; font-size:8pt;")
        fv.addWidget(tip)
        self.chk_fallback = QCheckBox(
            "FALLBACK — giữ DHCP/LLA,\nIP tĩnh làm dự phòng")
        self.chk_fallback.setToolTip(
            "0x00000054 = 0x3: camera thử DHCP→LLA trước,\n"
            "IP tĩnh làm dự phòng.\n"
            "Không tick = 0x0: vào thẳng IP tĩnh (tắt DHCP/LLA).")
        fv.addWidget(self.chk_fallback)
        fv.addSpacing(10)
        self.btn_snap = QPushButton("GRAB — CHỤP & KIỂM TRA")
        fv.addWidget(self.btn_snap)
        self.btn_live = QPushButton("LIVE VIEW")
        fv.addWidget(self.btn_live)
        self.btn_save_img = QPushButton("SAVE PNG (full-res)")
        self.btn_save_img.setEnabled(False)
        fv.addWidget(self.btn_save_img)
        fv.addStretch(1)
        h.addWidget(form_box, 1)
        return page

    def _build_image_tab(self) -> QWidget:
        page = QWidget()
        h = QHBoxLayout(page)
        h.setContentsMargins(14, 14, 14, 14)
        self.img_view = ImageView()
        h.addWidget(self.img_view, 3)

        right = QVBoxLayout()
        gb = QGroupBox("FRAME STATS")
        gvl = QVBoxLayout(gb)
        self.lbl_stats = QLabel("chưa có frame\nbấm GRAB hoặc LIVE")
        self.lbl_stats.setStyleSheet(
            f"color:{MUTED}; font-family:Consolas; font-size:10pt;")
        gvl.addWidget(self.lbl_stats)
        right.addWidget(gb)
        gb2 = QGroupBox("BRIGHTNESS HISTOGRAM")
        g2 = QVBoxLayout(gb2)
        self.hist = HistogramWidget()
        g2.addWidget(self.hist)
        right.addWidget(gb2)
        self.badge = QLabel("—")
        self.badge.setStyleSheet(
            f"color:{MUTED2}; border:1px solid {MUTED2}; font-family:Consolas;"
            f" font-weight:bold; padding:6px;")
        self.badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        right.addWidget(self.badge)
        right.addStretch(1)
        h.addLayout(right, 1)
        return page

    def _ip_edit(self, value):
        e = QLineEdit(value)
        e.setValidator(QRegularExpressionValidator(IP_RE, e))
        e.setAlignment(Qt.AlignmentFlag.AlignCenter)
        e.editingFinished.connect(lambda e=e: self._revalidate(e))
        return e

    # -------------------------------------------------------------- wiring

    def _connect(self):
        self.btn_scan.clicked.connect(self.scan)
        self.btn_forceip.clicked.connect(self.do_forceip)
        self.btn_perm.clicked.connect(self.do_setip)
        self.btn_regs.clicked.connect(self.do_readregs)
        self.btn_snap.clicked.connect(self.do_snapshot)
        self.btn_live.clicked.connect(self.toggle_live)
        self.btn_save_img.clicked.connect(self.do_save)
        self.dev_view.selectionModel().selectionChanged.connect(
            self._on_select)
        self.reg_view.doubleClicked.connect(self._on_reg_dbl)
        QShortcut("F5", self).activated.connect(self.scan)
        QShortcut("Ctrl+Return", self).activated.connect(self.do_setip)

    # -------------------------------------------------------------- status

    def set_busy(self, busy, label=""):
        self._busy = busy
        for b in (self.btn_scan, self.btn_forceip, self.btn_perm,
                  self.btn_regs, self.btn_snap, self.btn_live):
            b.setEnabled(not busy)
        if not self.last_snap:
            self.btn_save_img.setEnabled(False)
        self.st_right.setText(label or ("busy..." if busy else "ready"))
        self.st_right.setStyleSheet(
            f"color:{AMBER if busy else GREEN}; font-family:Consolas;")

    def _revalidate(self, edit):
        ok = gt.is_ipv4(edit.text().strip())
        edit.setProperty("invalid", "true" if not ok else "false")
        edit.style().unpolish(edit)
        edit.style().polish(edit)
        return ok

    # -------------------------------------------------------------- workers

    def _start(self, fn, label):
        if self._busy:
            return
        self.worker = Worker(fn, label, self)
        self.worker.log.connect(self.console.log)
        self.worker.done.connect(self._on_done)
        self.worker.fail.connect(self._on_fail)
        self.set_busy(True)
        self.worker.start()

    def _on_done(self, label, result):
        self.set_busy(False, label)
        if isinstance(result, list):
            self.cameras = result
            self.dev_model.set_devices(result)
            self.selected = None
            self.lbl_cam.setText("— NO DEVICE —")
            self.lbl_detail.setText("Click chọn camera")
            self.st["LINK"].setText("—")
            self.st["LINK"].setStyleSheet(
                f"color:{MUTED2}; font-family:Consolas;")
        elif isinstance(result, dict) and result.get("type") == "registers":
            self.reg_model.set_rows(result["rows"])
            n_ok = sum(1 for r in result["rows"] if r[4] != "err")
            self.console.log(
                f"Đọc xong {n_ok}/{len(result['rows'])} register",
                "ok" if n_ok == len(result["rows"]) else "warn")
        elif isinstance(result, dict) and result.get("type") == "snapshot":
            self._after_snapshot(result["data"])
        elif isinstance(result, tuple):
            self._after_setip(*result)

    def _on_fail(self, msg):
        self.set_busy(False, "ERROR")
        self.st_right.setStyleSheet(f"color:{RED}; font-family:Consolas;")
        self.console.log("LỖI: " + msg, "err")

    # -------------------------------------------------------------- select

    def _on_select(self):
        idx = self.dev_view.selectionModel().currentIndex()
        cam = self.dev_model.cam_at(idx.row())
        if not cam:
            return
        self.selected = cam
        self.lbl_cam.setText(f"{cam['manufacturer']} {cam['model']}")
        self.lbl_detail.setText(
            f"MAC {cam['mac']}\nIP  {cam['ip']} / {cam['subnet']}\n"
            f"S/N {cam['serial']} · FW {cam['firmware']}")
        self.e_ip.setText(cam["ip"])
        if gt.is_ipv4(cam["subnet"]) and cam["subnet"] != "0.0.0.0":
            self.e_mask.setText(cam["subnet"])
        self.e_gw.setText(cam["gateway"] if gt.is_ipv4(cam["gateway"])
                          else "0.0.0.0")
        self.st["LINK"].setText("UP")
        self.st["LINK"].setStyleSheet(f"color:{GREEN}; font-family:Consolas;")
        self.st["CAMERA"].setText(f"{cam['model']} @{cam['ip']}")
        self.st["CAMERA"].setStyleSheet(
            f"color:{ACCENT}; font-family:Consolas;")

    def _on_reg_dbl(self, index):
        if not index.isValid():
            return
        addr = self.reg_model.addr_at(index.row())
        dec = self.reg_model.decoded_at(index.row())
        if not gt.is_ipv4(dec):
            return
        target = {0x00000020: self.e_ip, 0x00000024: self.e_mask,
                  0x00000028: self.e_gw}.get(addr)
        if target is not None:
            target.setText(dec)
            self._revalidate(target)

    # -------------------------------------------------------------- actions

    def _require_cam(self):
        if self.selected is None:
            self.console.log("Chưa chọn camera.", "err")
            return None
        return dict(self.selected)

    def _validate(self):
        for e in (self.e_ip, self.e_mask, self.e_gw):
            if not self._revalidate(e):
                self.console.log(f"IP không hợp lệ: {e.text()}", "err")
                return None
        ip, mask = self.e_ip.text().strip(), self.e_mask.text().strip()
        gw = self.e_gw.text().strip() or "0.0.0.0"
        import ipaddress
        target = ipaddress.ip_address(ip)
        ifaces = gt.get_local_interfaces() or []
        if not any(target in ipaddress.ip_network(f"{ni}/{nm}", strict=False)
                   for ni, nm, _b in ifaces):
            self.console.log(
                f"CẢNH BÁO: {ip} ngoài subnet mọi card mạng — máy sẽ không "
                "thấy camera sau khi đổi. Đặt IP tĩnh cho NIC cùng subnet.",
                "warn")
        return ip, mask, gw

    def scan(self):
        if self._busy:
            return

        def job(progress):
            t0 = time.time()
            cams = gt.discover(timeout=3.0, progress=progress)
            rtt = (time.time() - t0) * 1000
            if not cams:
                progress("0 camera — kiểm tra nguồn/dây LAN; pylon Viewer "
                         "đang MỞ sẽ chiếm CCP", "warn")
            else:
                progress(f"{len(cams)} camera trả lời ACK "
                         f"(cửa sổ {rtt:.0f} ms)", "ok")
            return cams

        self.console.log("Discovery: broadcast 255.255.255.255 + multicast "
                         "224.0.0.112:3956", "info")
        self._start(job, "scan done")

    def do_forceip(self):
        cam = self._require_cam()
        v = self._validate()
        if not cam or not v:
            return
        ip, mask, gw = v
        if QMessageBox.question(
                self, "FORCEIP",
                f"Gán tạm IP {ip} cho {cam['mac']} ?\n"
                "(mất nguồn sẽ trở về IP cũ)") != QMessageBox.StandardButton.Yes:
            return

        def job(progress):
            progress("FORCEIP broadcast (không có ACK từ camera)...", "info")
            gt.send_forceip(cam["mac"], ip, mask, gw, progress=progress)
            progress("Chờ NIC camera reset (3s)...")
            time.sleep(3)
            cams = gt.discover(timeout=2.5, progress=progress)
            progress("QUÉT LẠI:", "info")
            for c in cams:
                progress(f"  {c['model']} @ {c['ip']}", "ok")
            return cams

        self.console.log(f"FORCEIP {cam['mac']} -> {ip}", "info")
        self._start(job, "forceip done")

    def do_setip(self):
        cam = self._require_cam()
        v = self._validate()
        if not cam or not v:
            return
        ip, mask, gw = v
        absolute = not self.chk_fallback.isChecked()
        if QMessageBox.question(
                self, "PWRITE — ghi non-volatile",
                f"Ghi IP vĩnh viễn {ip} / {mask} / {gw} vào {cam['ip']} ?\n\n"
                "Camera vẫn chạy IP cũ tới lần cấp nguồn kế tiếp.") \
                != QMessageBox.StandardButton.Yes:
            return

        def job(progress):
            with gt.CameraClient(cam["ip"],
                                 cam.get("interface_ip") or None) as c:
                info = c.get_bootstrap_info()
                progress(f"CCP ok · GV {info['spec_version']} · hiện tại: "
                         f"{info['current_mode']} · hỗ trợ: "
                         f"{info['supported']}", "info")
                progress("Ghi 0x20/0x24/0x28/0x54 + readback...", "info")
                new = c.set_persistent_ip(ip, mask, gw,
                                          absolute_static=absolute,
                                          progress=progress)
                rows = c.read_bootstrap_table()
            wr = {0x00000020, 0x00000024, 0x00000028, 0x00000054}
            self.pending_regs = [(a, n, r, d,
                                  "write" if a in wr else s)
                                 for a, n, r, d, s in rows]
            return cam, new, absolute

        self.console.log(f"PWRITE {cam['ip']} → {ip}...", "info")
        self._start(job, "pwrite done")

    def do_readregs(self):
        cam = self._require_cam()
        if not cam:
            return

        def job(progress):
            with gt.CameraClient(cam["ip"],
                                 cam.get("interface_ip") or None) as c:
                rows = c.read_bootstrap_table()
            progress(f"{len(rows)} register đọc qua GVCP", "info")
            return {"type": "registers", "rows": rows}

        self.console.log(f"READREG bootstrap của {cam['ip']}...", "info")
        self._start(job, "regs ok")

    # -------------------------------------------------------------- snapshot

    def do_snapshot(self):
        cam = self._require_cam()
        if not cam:
            return
        self.tabs.setCurrentIndex(1)

        def job(progress):
            import snapshot
            r = snapshot.grab_one(serial=cam["serial"], timeout_ms=6000,
                                  progress=progress)
            progress(r["verdict"], "ok" if "OK" in r["verdict"] else "warn")
            return {"type": "snapshot", "data": r}

        self.console.log(f"GRAB: mở {cam['model']} (S/N {cam['serial']}) "
                         "qua pylon...", "info")
        self._start(job, "grab done")

    def _after_snapshot(self, r):
        self.last_snap = r
        pix = self._pix_from_b64(r["preview_b64"])
        if pix is None:
            self.console.log("Không giải mã được preview", "err")
            return
        self.img_view.set_frame(pix, {"w": r["w"], "h": r["h"],
                                      "fmt": r["pixel_format"]})
        ok = r["std"] >= 8 or (r["std"] >= 2 and r["mean"] >= 8)
        self._set_badge(("PASS  ·  " if ok else "CHECK · ") + r["verdict"],
                        GREEN if ok else AMBER)
        self.lbl_stats.setText(
            f"RES      {r['w']} x {r['h']}\n"
            f"FMT      {r['pixel_format']}"
            f"  ({'color' if r['color'] else 'mono'})\n"
            f"BRIGHT   mean {r['mean']:.1f} / std {r['std']:.1f}\n"
            f"RANGE    min {r['min']}  max {r['max']}  /255\n"
            f"VERDICT  {'PASS' if ok else 'CHECK'}")
        try:
            self.hist.update_from_array(r["_full"])
        except Exception:
            pass
        self.btn_save_img.setEnabled(True)
        self.console.log(f"Frame {r['w']}x{r['h']} {r['pixel_format']} · "
                         f"{r['verdict']}", "ok" if ok else "warn")

    def do_save(self):
        if not self.last_snap:
            return
        from PySide6.QtWidgets import QFileDialog
        path, _ = QFileDialog.getSaveFileName(
            self, "Lưu ảnh", f"frame_{int(time.time())}.png",
            "PNG (*.png);;All (*.*)")
        if not path:
            return
        import snapshot
        with open(path, "wb") as fh:
            fh.write(snapshot.make_png_from_np(self.last_snap["_full"]))
        self.console.log(f"Đã lưu full-res: {path}", "ok")

    # -------------------------------------------------------------- live

    def toggle_live(self):
        if self._busy:
            return
        if self.live.session is not None:
            self.live.stop()
            self.console.log("Đang dừng live...", "info")
            return
        cam = self._require_cam()
        if not cam:
            return
        self.tabs.setCurrentIndex(1)
        self.live.start(cam["serial"])
        self.btn_live.setText("STOP LIVE")
        self.btn_live.setStyleSheet(f"color:{RED};")
        self.console.log(f"LIVE: {cam['model']} (S/N {cam['serial']})", "info")

    def _on_live_frame(self, b64, meta):
        pix = self._pix_from_b64(b64)
        if pix is None:
            return
        self.img_view.set_frame(pix, {"w": meta["w"], "h": meta["h"],
                                      "fmt": meta["fmt"]})
        self._set_badge(f"LIVE  {meta['fps']:.1f} fps", TEAL)
        self.lbl_stats.setText(
            f"RES      {meta['w']} x {meta['h']}\n"
            f"FMT      {meta['fmt']}\n"
            f"BRIGHT   mean {meta['mean']:.1f} / std {meta['std']:.1f}\n"
            f"FPS      {meta['fps']:.1f}")
        self.st["MODE"].setText(f"live {meta['fps']:.0f}fps")

    def _on_live_end(self, err):
        self.live.session = None
        self.btn_live.setText("LIVE VIEW")
        self.btn_live.setStyleSheet("")
        if err:
            self.console.log("LIVE lỗi: " + str(err), "err")
        else:
            self.console.log("Live đã dừng.", "muted")
        self.st["MODE"].setText("idle")

    # -------------------------------------------------------------- misc

    def _set_badge(self, text, color):
        self.badge.setText(text)
        self.badge.setStyleSheet(
            f"color:{color}; border:1px solid {color}; font-family:Consolas;"
            f" font-weight:bold; padding:6px;")

    @staticmethod
    def _pix_from_b64(b64):
        from PySide6.QtGui import QPixmap
        pix = QPixmap()
        return pix if pix.loadFromData(base64.b64decode(b64)) else None

    def _after_setip(self, cam, new, absolute):
        self.console.log("=" * 60, "muted")
        self.console.log(f"IP vĩnh viễn = {new['ip']} / {new['mask']} / "
                         f"{new['gw']}", "ok")
        self.console.log("Camera VẪN chạy IP cũ tới lần cấp nguồn kế tiếp. "
                         "Bấm FORCEIP với đúng IP vừa đặt để áp dụng ngay.",
                         "warn")
        self.console.log("Cấp nguồn lại camera => vào thẳng IP tĩnh."
                         if absolute else
                         "Camera thử DHCP/LLA trước, IP tĩnh dự phòng.",
                         "muted")
        if self.pending_regs:
            self.reg_model.set_rows(self.pending_regs)
        if new["ip"] != cam["ip"]:
            self.e_ip.setText(new["ip"])

    def closeEvent(self, ev):
        self.live.stop()
        super().closeEvent(ev)

    # -------------------------------------------------------------- about

    def show_about(self):
        QMessageBox.about(
            self, f"About {APP_NAME}",
            f"<h3>{APP_NAME} <span style='color:{MUTED2}'>v{APP_VERSION}"
            f"</span></h3>"
            f"<p><b>{VENDOR}</b> &nbsp;·&nbsp; "
            f"<span style='color:{MUTED}'>Industrial camera network tooling"
            f"</span></p>"
            f"<p style='color:{MUTED}'>Công cụ mạng cho camera GigE Vision "
            f"(Basler): quét GVCP, gán IP tạm (FORCEIP), đặt IP vĩnh viễn, "
            f"đọc bootstrap register, chụp &amp; kiểm tra hình, live view."
            f"</p>"
            f"<p style='color:{MUTED2}'>Copyright © 2026 {VENDOR}. "
            f"All rights reserved.<br>Built with Python · Qt6 "
            f"(PySide6) · pypylon</p>")

    def show_shortcuts(self):
        QMessageBox.information(
            self, "Keyboard shortcuts",
            "<table cellpadding='4'>"
            "<tr><td><b>F5</b></td><td>Quét camera (GVCP Discovery)</td></tr>"
            "<tr><td><b>Ctrl+Enter</b></td><td>PWRITE — đặt IP vĩnh viễn"
            "</td></tr>"
            "<tr><td><b>↑ / ↓</b></td><td>Chọn camera trong danh sách"
            "</td></tr></table>")


def main():
    try:
        sys.stdout.reconfigure(errors="replace")
    except Exception:
        pass
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setStyleSheet(QSS)
    w = MainWindow()
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
