"""Design tokens — giao diện kiểu engineering console (HMI/SCADA).

Nền rất tối, accent cyan, phân cấp bằng viền mảnh + chữ in hoa,
mọi giá trị kỹ thuật hiển thị bằng font monospace.
"""

FONT   = "Segoe UI"
MONO   = "Consolas"

# nền
BG      = "#0a0e14"   # nền gốc
PANEL   = "#10161f"   # panel chính
PANEL2  = "#151d29"   # panel con / ô nhập
PANEL3  = "#1b2534"   # hover / selection
FIELD   = "#0c1119"   # khung ảnh, console

# viền
BORDER  = "#1f2b3d"
BORDER2 = "#2b3b52"

# chữ
TEXT    = "#dbe4f0"
MUTED   = "#8494ab"
MUTED2  = "#5b6b82"

# tín hiệu (đèn HMI)
ACCENT    = "#00d4ff"   # cyan — action chính
ACCENT_H  = "#00a8cc"
GREEN     = "#3fb950"   # OK / LINK UP
AMBER     = "#e3b341"   # cảnh báo / busy
RED       = "#f85149"   # lỗi / LINK DOWN
TEAL      = "#14b8a6"   # live
VIOLET    = "#a78bfa"   # snapshot


def spaced(text, sep=" "):
    """Chữ in hoa giãn ký tự — mô phỏng letter-spacing của UI công nghiệp."""
    return sep.join(text.upper())
