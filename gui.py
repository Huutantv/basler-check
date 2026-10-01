"""GEV Console — giao diện kỹ thuật cho camera GigE Vision.

Phong cách HMI/engineering console: nền tối, giá trị monospace,
bảng bootstrap register, console log có timestamp, status bar.

Chạy:  python gui.py
"""

import queue
import threading
import tkinter as tk

import gigetools as gt
from theme import (ACCENT, ACCENT_H, AMBER, BG, BORDER, BORDER2, FIELD, FONT,
                   GREEN, MONO, MUTED, MUTED2, PANEL, PANEL2, PANEL3,
                   RED, TEAL, TEXT, VIOLET, spaced)
from widgets import (Badge, Button, Console, Entry, Histogram, Led,
                     RegisterTable, SectionHeader)

TAG2LEVEL = {"ok": " OK ", "err": "FAIL", "warn": "WARN",
             "info": "INFO", "muted": "DBUG"}


class Tab(tk.Label):
    def __init__(self, parent, text, command):
        super().__init__(parent, text=text, bg=PANEL, fg=MUTED,
                         font=(FONT, 9, "bold"), padx=16, pady=6,
                         cursor="hand2")
        self.command = command
        self.active = False
        self.bind("<Button-1>", lambda e: self.command())

    def set_active(self, active):
        self.active = active
        self.config(fg=ACCENT if active else MUTED,
                    bg=PANEL2 if active else PANEL)
        self.configure(highlightbackground=ACCENT if active else PANEL,
                       highlightcolor=ACCENT,
                       highlightthickness=0,
                       borderwidth=0)
        if not hasattr(self, "_bar"):
            self._bar = tk.Frame(self.master, bg=ACCENT, height=2)
        if active:
            self.update_idletasks()
            self._bar.place(x=self.winfo_x(), rely=1.0, width=self.winfo_width(),
                            anchor="sw")


class App:
    def __init__(self, root):
        self.root = root
        root.title("GEV CONSOLE — GigE Vision engineering tool")
        root.geometry("1180x820")
        root.minsize(1080, 740)
        root.configure(bg=BG)
        root.option_add("*Font", (FONT, 10))

        # status bar tạo sớm (side=bottom) — các hàm dựng sau có thể set_status
        bar = tk.Frame(self.root, bg=PANEL2, height=26)
        bar.pack(fill="x", side="bottom")
        self.st_cells = {}
        for i, key in enumerate(("LINK", "CAMERA", "NET", "MODE")):
            tk.Label(bar, text=key, bg=PANEL2, fg=MUTED2,
                     font=(FONT, 7, "bold")).pack(side="left", padx=(12, 4))
            v = tk.Label(bar, text="—", bg=PANEL2, fg=MUTED,
                         font=(MONO, 9))
            v.pack(side="left")
            tk.Frame(bar, bg=BORDER, width=1, height=16).pack(side="left", padx=10)
            self.st_cells[key] = v
        self.st_right = tk.Label(bar, text="ready", bg=PANEL2, fg=GREEN,
                                 font=(MONO, 9))
        self.st_right.pack(side="right", padx=12)

        self.cameras = []
        self.selected = None
        self.last_snap = None
        self.live = None
        self.q = queue.Queue()
        self.busy = False
        self.fallback_var = tk.BooleanVar(value=False)
        self._tabs = {}
        self._tab_frames = {}

        self._build()
        self._show_tab("DEVICE")
        self.root.after(80, self._poll)
        self.root.bind("<F5>", lambda e: self.scan())
        self.root.bind("<Up>", lambda e: self._cycle_selection(-1))
        self.root.bind("<Down>", lambda e: self._cycle_selection(1))
        self.root.bind("<Control-Return>", lambda e: self.do_setip())
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        self.log("Console sẵn sàng. SCAN = F5 · chọn camera = ↑/↓ · "
                 "PWRITE = Ctrl+Enter", "info")
        self.scan()

    def _on_close(self):
        if self.live:
            self.live.stop()
        self.root.destroy()

    # ------------------------------------------------------------- build

    def _build(self):
        # ================= HEADER =================
        top = tk.Frame(self.root, bg=PANEL, height=58)
        top.pack(fill="x")
        top.pack_propagate(False)

        head_left = tk.Frame(top, bg=PANEL)
        head_left.place(x=16, y=0, relheight=1)
        self.hdr_led = Led(head_left, size=14, bg_color=PANEL)
        self.hdr_led.pack(side="left", padx=(0, 10))
        tk.Label(head_left, text="GEV CONSOLE", bg=PANEL, fg=TEXT,
                 font=(FONT, 13, "bold")).pack(side="left")
        tk.Label(head_left, text="  |  Basler GigE Vision · GVCP · pylon",
                 bg=PANEL, fg=MUTED2, font=(MONO, 9)).pack(side="left")

        self.hdr_busy = tk.Label(top, text="", bg=PANEL, fg=AMBER,
                                 font=(FONT, 9, "bold"))
        self.hdr_busy.place(relx=1.0, x=-200, y=0, relheight=1, anchor="e")

        self.btn_scan = Button(top, "SCAN  [F5]", self.scan,
                               bg=PANEL3, fg=ACCENT, hover=BORDER2, height=32)
        self.btn_scan.place(relx=1.0, x=-16, y=13, width=120)

        # ================= BODY =================
        body = tk.Frame(self.root, bg=BG)
        body.pack(fill="both", expand=True, padx=12, pady=(10, 4))
        body.columnconfigure(0, weight=34)
        body.columnconfigure(1, weight=66)
        body.rowconfigure(0, weight=1)

        # ---------- CỘT TRÁI: device list + NIC ----------
        left = tk.Frame(body, bg=BG)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        left.rowconfigure(1, weight=1)
        left.columnconfigure(0, weight=1)

        lh = SectionHeader(left, "DEVICE LIST", "click / ↑↓")
        lh.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        self.count_lbl = tk.Label(lh, text="", bg=BG, fg=MUTED2, font=("Consolas", 8))
        self.count_lbl.pack(side="left", padx=(10, 0))

        self.list_panel = tk.Frame(left, bg=PANEL, highlightbackground=BORDER,
                                   highlightthickness=1)
        self.list_panel.grid(row=1, column=0, sticky="nsew")
        self.list_canvas = tk.Canvas(self.list_panel, bg=PANEL,
                                     highlightthickness=0, bd=0)
        self.list_canvas.pack(fill="both", expand=True)
        self.list_inner = tk.Frame(self.list_canvas, bg=PANEL)
        self._list_win = self.list_canvas.create_window(
            (0, 0), window=self.list_inner, anchor="nw")
        self.list_inner.bind("<Configure>", lambda e: self.list_canvas.configure(
            scrollregion=self.list_canvas.bbox("all")))
        self.list_canvas.bind("<Configure>", lambda e: self.list_canvas.itemconfig(
            self._list_win, width=e.width))

        def _wheel(ev):
            self.list_canvas.yview_scroll(-1 if ev.delta > 0 else 1, "units")
        for w in (self.list_canvas, self.list_inner, self.list_panel):
            w.bind("<MouseWheel>", _wheel)

        self.list_empty()

        nh = SectionHeader(left, "NETWORK INTERFACES")
        nh.grid(row=2, column=0, sticky="ew", pady=(10, 6))
        nic_card = tk.Frame(left, bg=PANEL, highlightbackground=BORDER,
                            highlightthickness=1)
        nic_card.grid(row=3, column=0, sticky="ew")
        self.nic_lbl = tk.Label(nic_card, text="", bg=PANEL, fg=MUTED,
                                font=("Consolas", 9), justify="left",
                                anchor="w", padx=10, pady=8)
        self.nic_lbl.pack(fill="x")
        self._show_nics()

        # ---------- CỘT PHẢI: tabs ----------
        right = tk.Frame(body, bg=PANEL, highlightbackground=BORDER,
                         highlightthickness=1)
        right.grid(row=0, column=1, sticky="nsew", padx=(6, 0))
        right.rowconfigure(1, weight=1)
        right.columnconfigure(0, weight=1)

        tab_bar = tk.Frame(right, bg=PANEL, height=30)
        tab_bar.grid(row=0, column=0, sticky="ew")
        tab_bar.grid_propagate(False)
        self._tab_bar = tab_bar
        for i, name in enumerate(("DEVICE", "IMAGE")):
            t = Tab(tab_bar, spaced(name), lambda n=name: self._show_tab(n))
            t.place(x=i * 110, rely=0.5, anchor="w")
            self._tabs[name] = t

        self.tab_body = tk.Frame(right, bg=PANEL)
        self.tab_body.grid(row=1, column=0, sticky="nsew", pady=(0, 0))
        self.tab_body.rowconfigure(0, weight=1)
        self.tab_body.columnconfigure(0, weight=1)

        self._build_device_tab()
        self._build_image_tab()

        # ================= CONSOLE =================
        bottom = tk.Frame(self.root, bg=BG)
        bottom.pack(fill="x", padx=12, pady=(4, 0))
        self.console = Console(bottom, height=7)
        self.console.pack(fill="x")

    # ---- tab DEVICE --------------------------------------------------

    def _build_device_tab(self):
        page = tk.Frame(self.tab_body, bg=PANEL)
        self._tab_frames["DEVICE"] = page
        page.columnconfigure(0, weight=1)
        page.columnconfigure(1, weight=1)

        # trái: thông tin camera
        info = tk.Frame(page, bg=PANEL)
        info.grid(row=0, column=0, sticky="nsew", padx=14, pady=12)
        info.columnconfigure(0, weight=1)

        head = tk.Frame(info, bg=PANEL)
        head.grid(row=0, column=0, sticky="ew")
        self.dot_canvas = Led(head, size=12, bg_color=PANEL)
        self.dot_canvas.pack(side="left", padx=(0, 8))
        self.cam_name = tk.Label(head, text="— NO DEVICE —", bg=PANEL, fg=TEXT,
                                 font=(FONT, 12, "bold"))
        self.cam_name.pack(side="left")

        self.cam_detail = tk.Label(info, text="SCAN để tìm camera (F5)",
                                   bg=PANEL, fg=MUTED, font=("Consolas", 9),
                                   justify="left", anchor="w", pady=6)
        self.cam_detail.grid(row=1, column=0, sticky="ew")

        SectionHeader(info, "BOOTSTRAP REGISTERS", "GVCP READREG").grid(
            row=2, column=0, sticky="ew", pady=(8, 4))
        self.reg_table = RegisterTable(info)
        self.reg_table.grid(row=3, column=0, sticky="ew")
        self.reg_table.set_rows([])
        self.btn_regs = Button(info, "READ REGISTERS", self.do_readregs,
                               bg=PANEL2, fg=ACCENT, hover=PANEL3, height=30)
        self.btn_regs.grid(row=4, column=0, sticky="ew", pady=(8, 0))

        # phải: form IP + hành động
        form = tk.Frame(page, bg=PANEL)
        form.grid(row=0, column=1, sticky="nsew", padx=14, pady=12)
        form.columnconfigure(0, weight=1)

        SectionHeader(form, "IP TARGET", "must match NIC subnet").grid(
            row=0, column=0, sticky="ew")
        grid = tk.Frame(form, bg=PANEL)
        grid.grid(row=1, column=0, sticky="ew", pady=(8, 0))
        grid.columnconfigure((0, 1, 2), weight=1, uniform="ip")
        entries = []
        for col, (label, val) in enumerate((("IP ADDRESS", "169.254.100.50"),
                                            ("SUBNET MASK", "255.255.0.0"),
                                            ("GATEWAY", "0.0.0.0"))):
            f = tk.Frame(grid, bg=PANEL)
            f.grid(row=0, column=col, sticky="ew",
                   padx=(0 if col == 0 else 8, 0))
            tk.Label(f, text=label, bg=PANEL, fg=MUTED2,
                     font=(FONT, 7, "bold")).pack(anchor="w", pady=(0, 4))
            ent = Entry(f, val, 13, validate=gt.is_ipv4)
            ent.pack(fill="x")
            entries.append(ent)
        self.e_ip, self.e_mask, self.e_gw = entries

        # checkbox fallback
        self.chk_wrap = tk.Frame(form, bg=PANEL, cursor="hand2")
        self.chk_wrap.grid(row=2, column=0, sticky="w", pady=(12, 0))
        self.chk_box = tk.Canvas(self.chk_wrap, width=16, height=16, bg=PANEL,
                                 highlightthickness=0)
        self.chk_box.pack(side="left", padx=(0, 8))
        tk.Label(self.chk_wrap,
                 text="FALLBACK — giữ DHCP/LLA, IP tĩnh làm dự phòng\n"
                      "không tick: vào thẳng IP tĩnh (tắt DHCP/LLA)",
                 bg=PANEL, fg=MUTED, font=(FONT, 8), justify="left"
                 ).pack(side="left")
        for w in (self.chk_wrap, self.chk_box):
            w.bind("<Button-1>", self._toggle_fallback)
        self._draw_check()

        tk.Frame(form, bg=BORDER, height=1).grid(row=3, column=0, sticky="ew",
                                                 pady=14)

        self.btn_force = Button(form, "FORCEIP  (tạm thời)", self.do_forceip,
                                bg=PANEL2, fg=TEXT, hover=PANEL3, height=36)
        self.btn_force.grid(row=4, column=0, sticky="ew")
        self.btn_perm = Button(form, "PWRITE — ĐẶT IP VĨNH VIỄN  [Ctrl+↵]",
                               self.do_setip, bg=ACCENT, fg=BG, hover=ACCENT_H,
                               height=36, font=(FONT, 9, "bold"))
        self.btn_perm.grid(row=5, column=0, sticky="ew", pady=(8, 0))
        tk.Label(form,
                 text="PWRITE = ghi register non-volatile (0x20/0x24/0x28/0x54)\n"
                      "camera vẫn chạy IP cũ tới lần cấp nguồn kế tiếp",
                 bg=PANEL, fg=MUTED2, font=(FONT, 8), justify="left"
                 ).grid(row=6, column=0, sticky="w", pady=(10, 0))

    def _draw_check(self):
        self.chk_box.delete("all")
        on = self.fallback_var.get()
        self.chk_box.create_rectangle(2, 2, 14, 14, outline=ACCENT if on else BORDER2,
                                      width=2)
        if on:
            self.chk_box.create_line(4, 8, 7, 12, fill=ACCENT, width=2)
            self.chk_box.create_line(7, 12, 13, 4, fill=ACCENT, width=2)

    def _toggle_fallback(self, _e=None):
        self.fallback_var.set(not self.fallback_var.get())
        self._draw_check()

    # ---- tab IMAGE ---------------------------------------------------

    def _build_image_tab(self):
        page = tk.Frame(self.tab_body, bg=PANEL)
        self._tab_frames["IMAGE"] = page
        page.columnconfigure(0, weight=58)
        page.columnconfigure(1, weight=42)
        page.rowconfigure(0, weight=1)

        # preview canvas + crosshair
        pv = tk.Frame(page, bg=PANEL)
        pv.grid(row=0, column=0, sticky="nsew", padx=14, pady=12)
        pv.rowconfigure(1, weight=1)
        pv.columnconfigure(0, weight=1)
        SectionHeader(pv, "FRAME PREVIEW", "crosshair @ tâm").grid(
            row=0, column=0, sticky="ew")
        self.preview_canvas = tk.Canvas(pv, bg=FIELD, highlightbackground=BORDER,
                                        highlightthickness=1)
        self.preview_canvas.grid(row=1, column=0, sticky="nsew")
        self.preview_canvas.bind("<Configure>", lambda e: self._redraw_overlay())
        self.preview_empty()

        self.verdict_badge = Badge(pv, "—", MUTED2, PANEL)
        self.verdict_badge.grid(row=2, column=0, sticky="w", pady=(8, 0))

        # stats phải
        st = tk.Frame(page, bg=PANEL)
        st.grid(row=0, column=1, sticky="nsew", padx=14, pady=12)
        st.columnconfigure(0, weight=1)

        SectionHeader(st, "FRAME STATS").grid(row=0, column=0, sticky="ew")
        self.stats_lbl = tk.Label(st, text="chưa có frame\n"
                                  "bấm GRAB hoặc LIVE",
                                  bg=PANEL, fg=MUTED, font=("Consolas", 10),
                                  justify="left", anchor="nw")
        self.stats_lbl.grid(row=1, column=0, sticky="ew", pady=(6, 10))

        SectionHeader(st, "BRIGHTNESS HISTOGRAM").grid(row=2, column=0,
                                                       sticky="ew")
        self.hist = Histogram(st, width=300, height=64)
        self.hist.grid(row=3, column=0, sticky="ew", pady=(6, 12))

        self.btn_snap = Button(st, "GRAB — CHỤP & KIỂM TRA", self.do_snapshot,
                               bg=VIOLET, fg="white", hover="#7c5cf0", height=36)
        self.btn_snap.grid(row=4, column=0, sticky="ew")
        self.btn_live = Button(st, "LIVE VIEW", self.toggle_live,
                               bg=TEAL, fg="white", hover="#0f9488", height=36)
        self.btn_live.grid(row=5, column=0, sticky="ew", pady=(8, 0))
        self.btn_save = Button(st, "SAVE PNG (full-res)", self.do_save,
                               bg=PANEL2, fg=MUTED, hover=PANEL3, height=36)
        self.btn_save.grid(row=6, column=0, sticky="ew", pady=(8, 0))
        self.btn_save.set_enabled(False)

    def preview_empty(self, msg="— NO FRAME —"):
        self.preview_canvas.delete("all")
        self._pv_img_id = None
        w = self.preview_canvas.winfo_width() or 500
        h = self.preview_canvas.winfo_height() or 300
        self.preview_canvas.create_text(w // 2, h // 2, text=msg, fill=MUTED2,
                                        font=(FONT, 10))

    def _show_frame(self, photo, meta=None):
        c = self.preview_canvas
        c.delete("all")
        w, h = c.winfo_width() or 500, c.winfo_height() or 300
        iw, ih = photo.width(), photo.height()
        k = min(1.0, (w - 24) / iw, (h - 24) / ih)
        self._photo = photo
        self._pv_img_id = c.create_image(w // 2, h // 2, image=photo, anchor="c")
        self._pv_scale = k
        self._pv_iw, self._pv_ih = iw, ih
        self._redraw_overlay(meta)

    def _redraw_overlay(self, meta=None):
        c = self.preview_canvas
        if not getattr(self, "_pv_img_id", None):
            return
        w, h = c.winfo_width(), c.winfo_height()
        cw, ch = self._pv_iw * self._pv_scale, self._pv_ih * self._pv_scale
        x0, y0 = (w - cw) / 2, (h - ch) / 2
        c.delete("overlay")
        c.create_rectangle(x0, y0, x0 + cw, y0 + ch, outline=BORDER2,
                           tags="overlay")
        # crosshair
        cx, cy = w / 2, h / 2
        arm = 14
        c.create_line(cx - arm, cy, cx + arm, cy, fill=GREEN, tags="overlay")
        c.create_line(cx, cy - arm, cx, cy + arm, fill=GREEN, tags="overlay")
        label = f"{self._pv_iw}x{self._pv_ih}" if not meta else \
            f"{meta.get('w')}x{meta.get('h')}  {meta.get('fmt','')}"
        c.create_text(x0 + 6, y0 + 8, text=label, anchor="nw", fill=GREEN,
                      font=("Consolas", 9), tags="overlay")

    # ---- tabs ---------------------------------------------------------

    def _show_tab(self, name):
        for n, f in self._tab_frames.items():
            if n == name:
                f.grid(row=0, column=0, sticky="nsew")
            else:
                f.grid_forget()
        for n, t in self._tabs.items():
            t.set_active(n == name)

    # ------------------------------------------------------------- helpers

    def set_status(self, key, text, color=MUTED):
        self.st_cells[key].config(text=text, fg=color)

    def log(self, msg, tag="muted"):
        self.console.log(msg, TAG2LEVEL.get(tag, "INFO"))

    def _show_nics(self):
        ifaces = gt.get_local_interfaces() or []
        if not ifaces:
            self.nic_lbl.config(text="(không phát hiện card mạng IPv4)")
            self.set_status("NET", "no IPv4 NIC", RED)
            return
        self.nic_lbl.config(
            text="\n".join(f"IPv4  {ip:<15} / {mask}" for ip, mask, _b in ifaces))
        self.set_status("NET", f"{len(ifaces)} NIC", GREEN)

    def list_empty(self, msg="NO DEVICE"):
        for w in self.list_inner.winfo_children():
            w.destroy()
        self.count_lbl.config(text="")
        box = tk.Frame(self.list_inner, bg=PANEL)
        box.pack(fill="x", padx=16, pady=24)
        tk.Label(box, text="◇", bg=PANEL, fg=BORDER2, font=(FONT, 20)).pack()
        tk.Label(box, text=msg, bg=PANEL, fg=MUTED, font=(MONO, 10)
                 ).pack(pady=(4, 2))
        tk.Label(box, text="SCAN (F5) để tìm camera", bg=PANEL, fg=MUTED2,
                 font=(FONT, 8)).pack()

    def _render_list(self):
        for w in self.list_inner.winfo_children():
            w.destroy()
        if not self.cameras:
            self.list_empty()
            return
        self.count_lbl.config(text=f"{len(self.cameras)} dev")
        for cam in self.cameras:
            sel = self.selected is cam
            bgc = PANEL3 if sel else PANEL
            card = tk.Frame(self.list_inner, bg=bgc, cursor="hand2")
            card.pack(fill="x", padx=0, pady=0)
            tk.Frame(card, bg=ACCENT if sel else bgc, width=3).pack(
                side="left", fill="y")
            body = tk.Frame(card, bg=bgc)
            body.pack(fill="x", padx=10, pady=7)
            led = Led(body, size=10, bg_color=bgc)
            led.set(GREEN if sel else MUTED2)
            led.pack(side="left", padx=(0, 8))
            left = tk.Frame(body, bg=bgc)
            left.pack(side="left", fill="x", expand=True)
            tk.Label(left, text=f"{cam['model'] or cam['serial']}",
                     bg=bgc, fg=TEXT if sel else MUTED,
                     font=(FONT, 10, "bold" if sel else "normal")).pack(anchor="w")
            tk.Label(left, text=f"S/N {cam['serial']} · FW {cam.get('firmware','—')}",
                     bg=bgc, fg=MUTED2, font=(MONO, 8)).pack(anchor="w")
            tk.Label(body, text=cam["ip"], bg=bgc,
                     fg=ACCENT if sel else TEXT,
                     font=(MONO, 11, "bold")).pack(side="right")
            for wdg in (card, body, left, led):
                wdg.bind("<Button-1>", lambda e, c=cam: self.select(c))
            for child in (left,):
                for cc in child.winfo_children():
                    cc.bind("<Button-1>", lambda e, c=cam: self.select(c))

    def _cycle_selection(self, step):
        if not self.cameras:
            return
        idxs = [i for i, c in enumerate(self.cameras) if c is self.selected]
        i = (idxs[0] if idxs else 0) + step
        i = max(0, min(len(self.cameras) - 1, i))
        self.select(self.cameras[i])

    def select(self, cam):
        self.selected = cam
        self._render_list()
        self.dot_canvas.set(GREEN)
        self.cam_name.config(text=f"{cam['manufacturer']} {cam['model']}")
        self.cam_detail.config(text=(
            f"MAC {cam['mac']}\n"
            f"IP  {cam['ip']} / {cam['subnet']}\n"
            f"S/N {cam['serial']} · FW {cam['firmware']}"))
        self.e_ip.set(cam["ip"])
        if gt.is_ipv4(cam["subnet"]) and cam["subnet"] != "0.0.0.0":
            self.e_mask.set(cam["subnet"])
        self.e_gw.set(cam["gateway"] if gt.is_ipv4(cam["gateway"]) else "0.0.0.0")
        self.set_status("LINK", "UP", GREEN)
        self.set_status("CAMERA", f"{cam['model']} @{cam['ip']}", ACCENT)

    def set_busy(self, busy, label=""):
        self.busy = busy
        for b in (self.btn_scan, self.btn_force, self.btn_perm,
                  self.btn_snap, self.btn_live, self.btn_regs):
            b.set_enabled(not busy)
        if not self.last_snap:
            self.btn_save.set_enabled(False)
        self.hdr_busy.config(text="● BUSY" if busy else "")
        self.st_right.config(
            text=label.strip() if label else ("busy..." if busy else "ready"),
            fg=AMBER if busy else GREEN)

    # ------------------------------------------------------------- workers

    def _run(self, fn, done_label):
        if self.busy:
            return
        self.set_busy(True)

        def work():
            try:
                result = fn(lambda m, t="info": self.q.put(("log", m, t)))
                self.q.put(("done", done_label, result))
            except gt.GVCPError as e:
                self.q.put(("err", str(e), None))
            except Exception as e:  # noqa: BLE001
                self.q.put(("err", f"{type(e).__name__}: {e}", None))

        threading.Thread(target=work, daemon=True).start()

    def _poll(self):
        try:
            while True:
                kind, msg, result = self.q.get_nowait()
                if kind == "log":
                    self.log(msg, result)
                elif kind == "done":
                    self.set_busy(False, msg)
                    if isinstance(result, list):
                        self.cameras = result
                        self.selected = None
                        self._render_list()
                        self.cam_name.config(text="— NO DEVICE —")
                        self.cam_detail.config(text="Click hoặc ↑/↓ để chọn.")
                        self.dot_canvas.set(MUTED2)
                        self.set_status("LINK", "—", MUTED2)
                        self.set_status("CAMERA", "—", MUTED)
                    elif isinstance(result, dict) and result.get("type") == "snapshot":
                        self._after_snapshot(result["data"])
                    elif isinstance(result, dict) and result.get("type") == "registers":
                        self.reg_table.set_rows(result["rows"])
                        n_ok = sum(1 for r in result["rows"] if r[4] != "err")
                        self.log(f"Đọc xong {n_ok}/{len(result['rows'])} register",
                                 "ok" if n_ok == len(result["rows"]) else "warn")
                    elif isinstance(result, tuple):
                        self._after_setip(*result)
                elif kind == "live":
                    self._show_live(msg, result)
                elif kind == "live_end":
                    self._live_stopped(msg)
                elif kind == "regs_write":
                    self.reg_table.set_rows(msg["rows"])
                elif kind == "err":
                    self.log("LỖI: " + msg, "err")
                    self.set_busy(False, "ERROR")
                    self.st_right.config(fg=RED)
        except queue.Empty:
            pass
        self.root.after(80, self._poll)

    # ------------------------------------------------------------- actions

    def scan(self):
        self.log("Discovery: broadcast 255.255.255.255 + multicast 224.0.0.112:3956",
                 "info")

        def job(progress):
            t0 = __import__("time").time()
            cams = gt.discover(timeout=3.0, progress=progress)
            rtt = (__import__("time").time() - t0) * 1000
            if not cams:
                progress("0 camera. Kiểm tra: nguồn, dây LAN; pylon Viewer đang "
                         "MỞ sẽ chiếm CCP.", "warn")
            else:
                progress(f"{len(cams)} camera trả lời ACK (cửa sổ {rtt:.0f} ms)",
                         "ok")
            return cams

        self._run(job, "scan done")

    def do_readregs(self):
        if self.selected is None:
            self.log("Chưa chọn camera.", "err")
            return
        cam = dict(self.selected)

        def job(progress):
            with gt.CameraClient(cam["ip"], cam.get("interface_ip") or None) as c:
                rows = c.read_bootstrap_table()
            return {"type": "registers", "rows": rows}

        self.log(f"READREG bootstrap của {cam['ip']}...", "info")
        self._run(job, "regs ok")

    def _validate(self):
        if self.selected is None:
            self.log("Chưa chọn camera.", "err")
            return None
        ip, mask = self.e_ip.get(), self.e_mask.get()
        gw = self.e_gw.get() or "0.0.0.0"
        for label, v in (("IP", ip), ("MASK", mask), ("GW", gw)):
            if not gt.is_ipv4(v):
                self.log(f"{label} không hợp lệ: {v}", "err")
                return None
        ifaces = gt.get_local_interfaces() or []
        import ipaddress
        target = ipaddress.ip_address(ip)
        if not any(target in ipaddress.ip_network(f"{ni}/{nm}", strict=False)
                   for ni, nm, _b in ifaces):
            self.log(f"CẢNH BÁO: {ip} ngoài subnet mọi card mạng — máy sẽ không "
                     "thấy camera sau khi đổi. Đặt IP tĩnh cho NIC cùng subnet.",
                     "warn")
        return ip, mask, gw

    def do_forceip(self):
        v = self._validate()
        if not v:
            return
        ip, mask, gw = v
        cam = dict(self.selected)

        def job(progress):
            progress("FORCEIP broadcast (không có ACK từ camera)...", "info")
            gt.send_forceip(cam["mac"], ip, mask, gw, progress=progress)
            import time as _t
            progress("Chờ NIC camera reset (3s)...")
            _t.sleep(3)
            cams = gt.discover(timeout=2.5, progress=progress)
            progress("QUÉT LẠI:", "info")
            for c in cams:
                progress(f"  {c['model']} @ {c['ip']}", "ok")
            return cams

        self.log(f"FORCEIP {cam['mac']} -> {ip} (mất nguồn = về IP cũ)", "info")
        self._run(job, "forceip done")

    def do_setip(self):
        v = self._validate()
        if not v:
            return
        ip, mask, gw = v
        cam = dict(self.selected)
        absolute = not self.fallback_var.get()

        def job(progress):
            with gt.CameraClient(cam["ip"], cam.get("interface_ip") or None) as c:
                info = c.get_bootstrap_info()
                progress(f"CCP ok · GV {info['spec_version']} · hiện tại: "
                         f"{info['current_mode']} · hỗ trợ: {info['supported']}",
                         "info")
                progress("Ghi 0x20/0x24/0x28/0x54 + readback...", "info")
                new = c.set_persistent_ip(
                    ip, mask, gw, absolute_static=absolute, progress=progress)
                rows = c.read_bootstrap_table()
            write_addrs = {0x00000020, 0x00000024, 0x00000028, 0x00000054}
            self.q.put(("regs_write", {"rows": [
                (a, n, r, d, "write" if a in write_addrs else s)
                for a, n, r, d, s in rows]}, None))
            return cam, new, absolute

        self.log(f"PWRITE {cam['ip']}: ghi IP vĩnh viễn {ip}...", "info")
        self._run(job, "pwrite done")

    def do_snapshot(self):
        if self.selected is None:
            self.log("Chưa chọn camera.", "err")
            return
        self._show_tab("IMAGE")
        cam = dict(self.selected)

        def job(progress):
            import snapshot
            r = snapshot.grab_one(serial=cam["serial"], timeout_ms=6000,
                                  progress=progress)
            progress(r["verdict"], "ok" if "OK" in r["verdict"] else "warn")
            return {"type": "snapshot", "data": r}

        self.log(f"GRAB: mở {cam['model']} (S/N {cam['serial']}) qua pylon...",
                 "info")
        self._run(job, "grab done")

    def _after_snapshot(self, r):
        self.last_snap = r
        try:
            photo = tk.PhotoImage(data=r["preview_b64"])
        except tk.TclError as e:
            self.log("Không giải mã được preview: " + str(e), "err")
            return
        meta = {"w": r["w"], "h": r["h"], "fmt": r["pixel_format"]}
        self._show_frame(photo, meta)
        ok = r["std"] >= 8 or (r["std"] >= 2 and r["mean"] >= 8)
        self.verdict_badge.set("PASS  ·  " + r["verdict"],
                               GREEN if ok else AMBER)
        self.stats_lbl.config(
            text=(f"RES      {r['w']} x {r['h']}\n"
                  f"FMT      {r['pixel_format']}  ({'color' if r['color'] else 'mono'})\n"
                  f"BRIGHT   mean {r['mean']:.1f} / std {r['std']:.1f}\n"
                  f"RANGE    min {r['min']}  max {r['max']}  /255\n"
                  f"VERDICT  {'PASS' if ok else 'CHECK'}"))
        try:
            self.hist.update(r["_full"])
        except Exception:
            pass
        self.log(f"Frame {r['w']}x{r['h']} {r['pixel_format']} · "
                 f"mean {r['mean']:.0f} · verdict: {r['verdict']}",
                 "ok" if ok else "warn")
        self.btn_save.set_enabled(True)

    def do_save(self):
        if not self.last_snap:
            return
        from tkinter import filedialog
        import time as _t
        path = filedialog.asksaveasfilename(
            title="Lưu ảnh", initialfile=f"frame_{int(_t.time())}.png",
            defaultextension=".png",
            filetypes=[("PNG", "*.png"), ("Tất cả", "*.*")])
        if not path:
            return
        import snapshot
        with open(path, "wb") as fh:
            fh.write(snapshot.make_png_from_np(self.last_snap["_full"]))
        self.log(f"Đã lưu full-res: {path}", "ok")

    # ------------------------------------------------------------- live

    def toggle_live(self):
        if self.busy:
            return
        if self.live is not None:
            self.live.stop()
            self.log("Dừng live...", "info")
            return
        if self.selected is None:
            self.log("Chưa chọn camera.", "err")
            return
        self._show_tab("IMAGE")
        cam = dict(self.selected)
        import snapshot
        self.live = snapshot.LiveSession(
            cam["serial"],
            lambda b64, meta: self.q.put(("live", b64, meta)),
            on_end=lambda err: self.q.put(("live_end", err, None)))
        self.live.start()
        self.btn_live.set_text("STOP LIVE")
        for b in (self.btn_scan, self.btn_force, self.btn_perm,
                  self.btn_snap, self.btn_save, self.btn_regs):
            b.set_enabled(False)
        self.log(f"LIVE: {cam['model']} (S/N {cam['serial']})", "info")

    def _show_live(self, b64, meta):
        try:
            photo = tk.PhotoImage(data=b64)
        except tk.TclError:
            return
        self._show_frame(photo, meta)
        self.verdict_badge.set(f"LIVE {meta['fps']:.1f} fps", TEAL)
        self.stats_lbl.config(
            text=(f"RES      {meta['w']} x {meta['h']}\n"
                  f"FMT      {meta['fmt']}\n"
                  f"BRIGHT   mean {meta['mean']:.1f} / std {meta['std']:.1f}\n"
                  f"FPS      {meta['fps']:.1f} (EMA)"))
        self.set_status("MODE", f"live {meta['fps']:.0f}fps", TEAL)

    def _live_stopped(self, err):
        self.live = None
        self.btn_live.set_text("LIVE VIEW")
        for b in (self.btn_scan, self.btn_force, self.btn_perm,
                  self.btn_snap, self.btn_regs):
            b.set_enabled(not self.busy)
        if err:
            self.log("LIVE lỗi: " + str(err), "err")
        else:
            self.log("Live đã dừng.", "muted")
        self.set_status("MODE", "idle", MUTED)

    def _after_setip(self, cam, new, absolute):
        self.log("=" * 60, "muted")
        self.log(f"IP vĩnh viễn = {new['ip']} / {new['mask']} / {new['gw']}", "ok")
        self.log("Camera VẪN chạy IP cũ tới lần cấp nguồn kế tiếp. "
                 "Bấm FORCEIP với đúng IP vừa đặt để áp dụng ngay.", "warn")
        self.log("Cấp nguồn lại camera => vào thẳng IP tĩnh." if absolute
                 else "Camera sẽ thử DHCP/LLA trước, IP tĩnh làm dự phòng.", "muted")
        if new["ip"] != cam["ip"]:
            self.e_ip.set(new["ip"])


def main():
    import sys
    try:
        sys.stdout.reconfigure(errors="replace")
    except Exception:
        pass
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
