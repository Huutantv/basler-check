"""Widgets dùng chung — phong cách engineering console (Tkinter thuần).

Button, Entry, Led, Badge, SectionHeader, Console (log có timestamp +
filter level), RegisterTable, Histogram.
"""

import time
import tkinter as tk

from theme import (ACCENT, AMBER, BG, BORDER, BORDER2, FIELD, FONT, GREEN,
                   MONO, MUTED, MUTED2, PANEL, PANEL2, RED, TEXT,
                   spaced)


class Button(tk.Frame):
    """Nút phẳng, label in hoa. hover/disabled đổi màu nền."""

    def __init__(self, parent, text, command=None, bg=PANEL2, fg=TEXT,
                 hover=None, height=34, font=(FONT, 9, "bold"), border=None,
                 mono=False):
        super().__init__(parent, bg=border or BORDER, bd=0, highlightthickness=0)
        self.command = command
        self.base_bg, self.hover_bg, self.fg = bg, hover or bg, fg
        self.disabled = False
        self.inner = tk.Frame(self, bg=bg, height=height)
        self.inner.pack(fill="both", expand=True, padx=1, pady=1)
        self.inner.pack_propagate(False)
        self.label = tk.Label(self.inner, text=text, bg=bg, fg=fg,
                              font=font if not mono else (MONO, 9, "bold"))
        self.label.place(relx=0.5, rely=0.5, anchor="center")
        for w in (self, self.inner, self.label):
            w.bind("<Enter>", self._on_enter)
            w.bind("<Leave>", self._on_leave)
            w.bind("<Button-1>", self._click)
        self._apply_state()

    def set_text(self, text):
        self.label.config(text=text)

    def set_enabled(self, en):
        self.disabled = not en
        cur = "hand2" if en else ""
        self.config(cursor=cur)
        self.label.config(cursor=cur)
        self._apply_state()

    def _apply_state(self):
        if self.disabled:
            self.inner.config(bg=PANEL2)
            self.label.config(bg=PANEL2, fg=MUTED2)
        else:
            self.inner.config(bg=self.base_bg)
            self.label.config(bg=self.base_bg, fg=self.fg)

    def _on_enter(self, _e):
        if not self.disabled:
            self.inner.config(bg=self.hover_bg)
            self.label.config(bg=self.hover_bg)

    def _on_leave(self, _e):
        if not self.disabled:
            self.inner.config(bg=self.base_bg)
            self.label.config(bg=self.base_bg)

    def _click(self, _e):
        if not self.disabled and self.command:
            self.command()


class Entry(tk.Frame):
    """Ô nhập monospace, viền đổi màu theo focus / valid."""

    def __init__(self, parent, value="", width=14, validate=None):
        super().__init__(parent, bg=PANEL2, highlightbackground=BORDER,
                         highlightcolor=ACCENT, highlightthickness=1, bd=0)
        self._validate = validate
        self.var = tk.StringVar(value=value)
        self.e = tk.Entry(self, textvariable=self.var, bg=PANEL2, fg=TEXT,
                          insertbackground=ACCENT, relief="flat", width=width,
                          font=(MONO, 10), justify="center")
        self.e.pack(fill="x", ipady=5, padx=2, pady=1)
        self.e.bind("<FocusIn>", lambda e: self.config(highlightbackground=ACCENT))
        self.e.bind("<FocusOut>", lambda e: (self.config(highlightbackground=BORDER),
                                             self._revalidate()))
        if validate:
            self.e.bind("<KeyRelease>", lambda e: self._revalidate())

    def _revalidate(self):
        if not self._validate:
            return
        ok = self._validate(self.var.get().strip())
        self.config(highlightbackground=BORDER if ok else RED)

    def get(self):
        return self.var.get().strip()

    def set(self, v):
        self.var.set(v)
        self._revalidate()


class Led(tk.Canvas):
    """Đèn trạng thái HMI — vòng ngoài tối, lõi màu khi sáng."""

    def __init__(self, parent, size=10, bg_color=PANEL):
        super().__init__(parent, width=size, height=size, bg=bg_color,
                         highlightthickness=0)
        self.size = size
        self.set(MUTED2)

    def set(self, color):
        self.delete("all")
        s = self.size
        self.create_oval(1, 1, s - 1, s - 1, outline=BORDER2, width=1)
        self.create_oval(3, 3, s - 3, s - 3, fill=color, outline="")


class Badge(tk.Label):
    """Nhãn giá trị kỹ thuật (đỏ/xanh theo trạng thái)."""

    def __init__(self, parent, text="", color=MUTED, bg_color=PANEL,
                 font=(MONO, 9, "bold")):
        super().__init__(parent, text=text, bg=bg_color, fg=color, font=font,
                         padx=7, pady=2, highlightbackground=color,
                         highlightthickness=1)

    def set(self, text, color):
        self.config(text=text, fg=color, highlightbackground=color)


class SectionHeader(tk.Frame):
    """Header panel: tiêu đề in hoa giãn ký tự + nhãn phụ phải."""

    def __init__(self, parent, title, right="", bg_color=BG):
        super().__init__(parent, bg=bg_color)
        tk.Label(self, text=spaced(title), bg=bg_color, fg=MUTED,
                 font=(FONT, 8, "bold")).pack(side="left")
        if right:
            tk.Label(self, text=right, bg=bg_color, fg=MUTED2,
                     font=(MONO, 8)).pack(side="right")


class Console(tk.Frame):
    """Log kỹ thuật: [HH:MM:SS.mmm] [LEVEL] msg. Filter theo level, có Clear."""

    LEVEL_COLORS = {"INFO": ACCENT, " OK ": GREEN, "WARN": AMBER,
                    "FAIL": RED, "DBUG": MUTED2}
    LEVELS = ("INFO", " OK ", "WARN", "FAIL", "DBUG")

    def __init__(self, parent, height=9, filterable=True):
        super().__init__(parent, bg=PANEL, highlightbackground=BORDER,
                         highlightthickness=1)
        self._filter = None
        head = tk.Frame(self, bg=PANEL)
        head.pack(fill="x", padx=8, pady=(5, 2))
        tk.Label(head, text=spaced("console", sep=" "), bg=PANEL, fg=MUTED,
                 font=(FONT, 8, "bold")).pack(side="left")
        self._count_lbl = tk.Label(head, text="", bg=PANEL, fg=MUTED2,
                                   font=(MONO, 8))
        self._count_lbl.pack(side="right", padx=(6, 0))
        self._btn_clear = tk.Label(head, text="  CLEAR  ", bg=PANEL, fg=MUTED2,
                                   font=(FONT, 8, "bold"), cursor="hand2")
        self._btn_clear.pack(side="right")
        self._btn_clear.bind("<Button-1>", lambda e: self.clear())
        if filterable:
            self._filter_lbl = tk.Label(head, text="  FILTER: ALL  ", bg=PANEL,
                                        fg=ACCENT, font=(FONT, 8, "bold"),
                                        cursor="hand2")
            self._filter_lbl.pack(side="right", padx=(6, 0))
            self._filter_lbl.bind("<Button-1>", self._cycle_filter)

        body = tk.Frame(self, bg=PANEL)
        body.pack(fill="both", expand=True, padx=(8, 4), pady=(0, 6))
        self.box = tk.Text(body, bg=PANEL, fg=TEXT, relief="flat",
                           font=(MONO, 9), state="disabled", wrap="none",
                           highlightthickness=0, bd=0, padx=4, pady=4,
                           height=height)
        sb = tk.Scrollbar(body, command=self.box.yview, width=8)
        self.box.configure(yscrollcommand=sb.set, takefocus=0)
        sb.pack(side="right", fill="y")
        self.box.pack(side="left", fill="both", expand=True)
        for lvl, color in self.LEVEL_COLORS.items():
            self.box.tag_configure(lvl.strip(), foreground=color)
        self.box.tag_configure("TS", foreground=MUTED2)
        self._n = 0
        self._history = []

    def _cycle_filter(self, _e=None):
        if self._filter is None:
            self._filter = "WARN"
        elif self._filter == "WARN":
            self._filter = "FAIL"
        else:
            self._filter = None
        self._filter_lbl.config(
            text=f"  FILTER: {'ALL' if self._filter is None else self._filter}  ")
        self._redraw()

    def _match(self, level):
        if self._filter is None:
            return True
        return level.strip() == self._filter

    def log(self, msg, level="INFO"):
        level = level if level in self.LEVEL_COLORS else "INFO"
        ts = time.strftime("%H:%M:%S") + ".%03d" % (int(time.time() * 1000) % 1000)
        self._n += 1
        self._count_lbl.config(text=f"{self._n} dòng")
        self._history.append((ts, level, msg))
        if self._match(level):
            self._append(ts, level, msg)

    def _append(self, ts, level, msg):
        self.box.config(state="normal")
        self.box.insert("end", f"[{ts}] ", "TS",
                        f"[{level}] ", level.strip(), f"{msg}\n")
        self.box.see("end")
        self.box.config(state="disabled")

    def _redraw(self):
        self.box.config(state="normal")
        self.box.delete("1.0", "end")
        for line in self._history:
            ts, level, msg = line
            if self._match(level):
                self._append(ts, level, msg)
        self.box.config(state="disabled")

    def clear(self):
        self.box.config(state="normal")
        self.box.delete("1.0", "end")
        self.box.config(state="disabled")
        self._n = 0
        self._history = []
        self._count_lbl.config(text="")


class RegisterTable(tk.Frame):
    """Bảng bootstrap register: ADDR · NAME · RAW (hex) · DECODED.

    set_rows(rows): rows = list of (addr, name, raw_int or None, decoded, status)
    status: 'ok' | 'write' | 'err' | '' — đổi màu dòng (write = vừa ghi).
    """

    COLS = (("addr", 90), ("name", 230), ("raw", 130), ("dec", 220))
    HEAD_FONT = (MONO, 8, "bold")

    def __init__(self, parent, bg_color=PANEL):
        super().__init__(parent, bg=bg_color, highlightbackground=BORDER,
                         highlightthickness=1)
        self.bg_color = bg_color
        head = tk.Frame(self, bg=PANEL2, height=20)
        head.pack(fill="x")
        head.pack_propagate(False)
        for name, x in zip(("ADDR", "NAME", "RAW", "DECODED"),
                           (8, 98, 328, 458)):
            tk.Label(head, text=name, bg=PANEL2, fg=MUTED,
                     font=self.HEAD_FONT).place(x=x, rely=0.5, anchor="w")
        self._rows_frame = tk.Frame(self, bg=bg_color)
        self._rows_frame.pack(fill="both", expand=True)
        self.configure(width=680)

    def set_rows(self, rows):
        for w in self._rows_frame.winfo_children():
            w.destroy()
        if not rows:
            tk.Label(self._rows_frame, text="— chưa đọc —  bấm READ REGISTERS",
                     bg=self.bg_color, fg=MUTED2, font=(MONO, 9)
                     ).pack(anchor="w", padx=8, pady=10)
            return
        for addr, name, raw, decoded, status in rows:
            row = tk.Frame(self._rows_frame, bg=self.bg_color, height=22)
            row.pack(fill="x")
            row.pack_propagate(False)
            color = {"ok": TEXT, "write": ACCENT, "err": RED}.get(status, MUTED)
            cells = ((8, f"0x{addr:08X}" if addr is not None else "—", MUTED),
                     (98, name, color),
                     (328, "—" if raw is None else f"0x{raw:08X}", color),
                     (458, decoded, color))
            for x, text, col in cells:
                tk.Label(row, text=text, bg=self.bg_color, fg=col,
                         font=(MONO, 9)).place(x=x, rely=0.5, anchor="w")
            tk.Frame(row, bg=BORDER, height=1).place(relx=0, rely=1.0,
                                                     relwidth=1.0, anchor="sw")


class Histogram(tk.Canvas):
    """Biểu đồ phân bố độ sáng vẽ bằng Canvas (không cần matplotlib).

    update(arr): arr = numpy array (h,w[,3]) uint8 — tính hist 32 bin trên Canvas.
    """

    def __init__(self, parent, width=250, height=56, bg_color=FIELD):
        super().__init__(parent, width=width, height=height, bg=bg_color,
                         highlightbackground=BORDER, highlightthickness=1)
        self.bind("<Configure>", lambda e: self._redraw_last())

    def update(self, arr):
        import numpy as np
        flat = arr[..., 0] if arr.ndim == 3 else arr
        hist, _ = np.histogram(flat.ravel(), bins=32, range=(0, 256))
        self._last = hist.tolist()
        self._redraw_last()

    def _redraw_last(self):
        self.delete("all")
        hist = getattr(self, "_last", None)
        if not hist:
            return
        w = self.winfo_width() or int(self["width"])
        h = self.winfo_height() or int(self["height"])
        peak = max(hist) or 1
        n = len(hist)
        bw = max(1, (w - 4) // n)
        for i, v in enumerate(hist):
            bh = int((h - 10) * v / peak)
            x0 = 2 + i * bw
            col = GREEN if i < 16 else (AMBER if i < 26 else RED)
            self.create_rectangle(x0, h - 2 - bh, x0 + bw - 1, h - 2,
                                  fill=col, outline="")
        self.create_line(2, h - 2, w - 2, h - 2, fill=BORDER2)
