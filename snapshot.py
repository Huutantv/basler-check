"""Chup va kiem tra anh tu camera GigE qua pypylon (SDK Basler).

- Camera mau (duoi 'gc' = color, sensor Bayer): tu dong chuyen Bayer -> RGB
- Camera trang den (duoi 'gm'): Mono8 truc tiep
- grab_one(): 1 frame + ket luan anh; LiveSession(): stream lien tuc
- Xuat PNG chuan (khong dung PIL) de hien trong Tk PhotoImage.
"""

import base64
import struct
import threading
import time
import zlib

import numpy as np
import pypylon.pylon as pylon


class SnapshotError(Exception):
    pass


# ---------------------------------------------------------------- PNG

def _png_chunk(typ, data):
    return (struct.pack("!I", len(data)) + typ + data
            + struct.pack("!I", zlib.crc32(typ + data) & 0xFFFFFFFF))


def make_png(w, h, buf, stride, channels):
    ct = 0 if channels == 1 else 2
    raw = bytearray()
    for y in range(h):
        raw.append(0)
        raw += buf[y * stride: y * stride + w * channels]
    ihdr = struct.pack("!IIBBBBB", w, h, 8, ct, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n"
            + _png_chunk(b"IHDR", ihdr)
            + _png_chunk(b"IDAT", zlib.compress(bytes(raw), 3))
            + _png_chunk(b"IEND", b""))


def make_png_from_np(arr):
    """arr: (h,w) uint8 hoac (h,w,3) uint8 C-contiguous."""
    if arr.ndim == 2:
        return make_png(arr.shape[1], arr.shape[0], arr.tobytes(),
                        arr.shape[1], 1)
    return make_png(arr.shape[1], arr.shape[0], arr.tobytes(),
                    arr.shape[1] * 3, 3)


# ---------------------------------------------------------------- camera

def find_device(serial=None):
    f = pylon.TlFactory.GetInstance()
    devs = list(f.EnumerateDevices())
    if not devs:
        raise SnapshotError(
            "Khong tim thay camera nao trong pylon. "
            "Kiem tra day LAN / nguon camera / IP cung subnet.")
    if serial:
        for d in devs:
            if serial in d.GetFriendlyName():
                return d
        raise SnapshotError(
            f"Khong thay camera S/N {serial} trong danh sach pylon: "
            + "; ".join(d.GetFriendlyName() for d in devs))
    return devs[0]


def _pixel_format_candidates():
    return ["Bgr8", "BayerGR8", "BayerRG8", "BayerGB8", "BayerBG8", "Mono8"]


def choose_pixel_format(cam):
    """Chon dinh dang hinh tot nhat camera ho tro (mau truoc, den sau)."""
    try:
        if cam.PixelFormat.IsWritable():
            for want in _pixel_format_candidates():
                try:
                    cam.PixelFormat.SetValue(want)
                    return want
                except Exception:
                    continue
    except Exception:
        pass
    return None


def _bayer_to_rgb(arr, pattern):
    """Don gian 2x2 — fix tran uint8 (200+200 -> 72)."""
    p = pattern[5:8]  # 'GR8', 'RG8', 'GB8', 'BG8'
    # cat le neu anh le kich thuoc
    h, w = arr.shape
    h2, w2 = h & ~1, w & ~1
    if h2 != h or w2 != w:
        arr = np.ascontiguousarray(arr[:h2, :w2])
    a00, a01, a10, a11 = (arr[0::2, 0::2], arr[0::2, 1::2],
                          arr[1::2, 0::2], arr[1::2, 1::2])
    # tinh G trung binh bang uint16 tranh tran 8-bit
    def avg(a, b):
        return ((a.astype(np.uint16) + b.astype(np.uint16)) // 2).astype(np.uint8)

    if p == "GR8":     # rows: G R / B G
        R, G, B = a01, avg(a00, a11), a10
    elif p == "RG8":   # rows: R G / G B
        R, G, B = a00, avg(a01, a10), a11
    elif p == "GB8":   # rows: G B / R G
        R, G, B = a10, avg(a00, a11), a01
    else:              # BG8: rows: B G / G R
        R, G, B = a11, avg(a01, a10), a00

    def quad(a):
        return np.repeat(np.repeat(a, 2, axis=0), 2, axis=1)

    R, G, B = quad(R), quad(G), quad(B)
    hh, ww = R.shape
    out = np.empty((hh, ww, 3), np.uint8)
    out[:, :, 0] = R
    out[:, :, 1] = G
    out[:, :, 2] = B
    return out


def image_to_array(img, fmt):
    """-> (ndarray, fmt_ten). RGB (h,w,3) voi Bgr8/Bayer, (h,w) voi Mono."""
    w, h = int(img.GetWidth()), int(img.GetHeight())
    fmt = fmt or f"0x{int(img.GetPixelType()):08X}"
    # uu tien dung Pylon ImageFormatConverter de debayer chuan (tranh loi uint8 + mau hong)
    if "Bayer" in fmt:
        try:
            conv = pylon.ImageFormatConverter()
            conv.OutputPixelFormat = pylon.PixelType_RGB8packed
            conv.OutputBitAlignment = pylon.OutputBitAlignment_MsbAligned
            out = conv.Convert(img)
            ow, oh = int(out.GetWidth()), int(out.GetHeight())
            arr = np.frombuffer(out.GetBuffer(), np.uint8).reshape(oh, ow, 3)
            return np.ascontiguousarray(arr), fmt
        except Exception:
            pass  # fallback duoi

    imgsize = int(img.GetImageSize())
    buf = bytes(img.GetBuffer())
    bpp = imgsize // (w * h) if w * h and imgsize % (w * h) == 0 else 0
    if bpp == 3:  # Bgr8 truc tiep tu camera
        arr = np.frombuffer(buf[:w * h * 3], np.uint8).reshape(h, w, 3)
        return np.ascontiguousarray(arr[:, :, ::-1]), fmt  # BGR -> RGB
    if bpp == 2:  # Mono10/12 hoac Bayer10/12 packed 16-bit: lay byte cao
        hi = np.frombuffer(buf, np.uint8)[1::2][:h * (imgsize // h // 2)]
        plane = hi.reshape(h, imgsize // h // 2)[:, :w]
        if "Bayer" in fmt:
            return _bayer_to_rgb(np.ascontiguousarray(plane), fmt), fmt
        return np.ascontiguousarray(plane), fmt
    stride = imgsize // h if imgsize % h == 0 else w
    plane = np.frombuffer(buf[:stride * h], np.uint8).reshape(h, stride)[:, :w]
    if "Bayer" in fmt:
        return _bayer_to_rgb(np.ascontiguousarray(plane), fmt), fmt
    return np.ascontiguousarray(plane), fmt


def use_full_resolution(cam):
    for name in ("Width", "Height"):
        try:
            p = getattr(cam, name)
            if p.IsWritable():
                try:
                    p.SetToMaximum()
                except Exception:
                    p.SetValue(p.GetMax())
        except Exception:
            pass


def _open_camera(serial):
    dev = find_device(serial)
    f = pylon.TlFactory.GetInstance()
    last = None
    for _ in range(3):
        cam = pylon.InstantCamera(f.CreateDevice(dev))
        try:
            cam.Open()
            return cam, dev
        except Exception as e:
            last = e
            time.sleep(2)
    msg = str(last)
    if "another application" in msg or "0xE1018006" in msg:
        msg = ("Camera dang bi ung dung khac giu (GUI khac / pylon Viewer). "
               "Dong cua do lai roi thu.")
    elif "imeout" in msg:
        msg = ("Camera khong phan hoi khi mo. Windows Firewall co the "
               "dang chan UDP ve may.")
    raise SnapshotError("Mo camera that bai: " + msg)


def _grab_retrying(cam, timeout_ms):
    try:
        img = cam.GrabOne(timeout_ms)
    except Exception as e:
        if "imeout" in type(e).__name__ or "imeout" in str(e):
            import sys
            raise SnapshotError(
                "Camera mở được nhưng không thấy luồng ảnh (timeout). "
                "Nguyên nhân số 1: Windows Firewall chặn UDP luồng ảnh về "
                "máy. Chạy lệnh sau trong PowerShell Admin:\n  netsh "
                "advfirewall firewall add rule name=\"GigE Vision\" "
                "dir=in action=allow program=\""
                + sys.executable + "\" enable=yes")
        raise
    if not img.IsValid():
        raise SnapshotError("Frame không hợp lệ (timeout?)")
    return img


# ---------------------------------------------------------------- snapshot


def grab_one(serial=None, timeout_ms=3000, preview_side=400, progress=None):
    def say(msg, tag="info"):
        if progress:
            try:
                progress(msg, tag)
            except TypeError:
                progress(msg)

    cam, dev = _open_camera(serial)
    say(f"Đang mở: {dev.GetFriendlyName()}")
    try:
        fmt = choose_pixel_format(cam)
        use_full_resolution(cam)
        try:
            cam.TriggerMode.SetValue("Off")
        except Exception:
            pass

        attempts = 0
        while True:
            attempts += 1
            if attempts == 1:
                say("Đang chụp frame đầu tiên...")
            else:
                say(f"Khung hình đồng nhất — thử chỉnh exposure "
                    f"(lần {attempts - 1})...")
                fixed = False
                try:
                    cam.ExposureAuto.SetValue("Once")
                    fixed = True
                except Exception:
                    try:
                        cur = int(cam.ExposureTime.GetValue())
                        cam.ExposureTime.SetValue(min(cur * 6 + 1000, 1000000))
                        fixed = True
                    except Exception:
                        pass
                if not fixed:
                    say("Camera không cho chỉnh exposure — dùng ảnh hiện tại")
                    break
                time.sleep(0.6)

            img = _grab_retrying(cam, timeout_ms)
            arr, fmt_name = image_to_array(img, fmt)
            mean = float(arr.mean())
            std = float(arr.std())
            w, h = arr.shape[1], arr.shape[0]
            say(f"Frame {w}x{h} {fmt_name} — độ sáng TB {mean:.0f}/255, "
                f"lệch chuẩn {std:.0f}")
            if std >= 8 or (std >= 2 and mean >= 8) or attempts >= 4:
                break

        has_content = std >= 8 or (std >= 2 and mean >= 8)
        if not has_content:
            verdict = (f"Camera XUẤT HÌNH nhưng khung hình TỐI ĐEN "
                       f"(mean {mean:.0f}, chỉ thấy nhiễu) — ống kính đang "
                       f"che hoặc phòng tối (đã thử chỉnh exposure "
                       f"{attempts - 1} lần)" if mean < 8 else
                       f"Camera XUẤT HÌNH nhưng trắng xóa ({mean:.0f}/255) — "
                       "quá sáng hoặc hở sáng")
        else:
            kind = "màu" if arr.ndim == 3 else "trắng đen"
            verdict = (f"Camera NHẬN HÌNH OK — ảnh {kind} có chi tiết "
                       f"(lệch chuẩn {std:.0f})")

        k = max(1, -(-max(w, h) // preview_side))
        prev = np.ascontiguousarray(arr[::k, ::k])
        png = make_png_from_np(prev)
        flat = arr.reshape(-1)
        return {
            "model": dev.GetFriendlyName(),
            "serial": serial,
            "w": w, "h": h,
            "pixel_format": fmt_name,
            "min": int(flat.min()), "max": int(flat.max()),
            "mean": mean, "std": std,
            "color": arr.ndim == 3,
            "verdict": verdict,
            "preview": png,
            "preview_b64": base64.b64encode(png).decode(),
            "preview_ext": ".png",
            "_full": arr,
        }
    finally:
        cam.Close()


# ---------------------------------------------------------------- live


class LiveSession:
    """Stream lien tuc: mo 1 lan, grab lap lap, goi frame_cb(png_b64, meta).

    Dung: session = LiveSession(serial, frame_cb); session.start();
    dung: session.stop()
    """

    def __init__(self, serial, frame_cb, on_end=None, preview_side=460):
        self.serial = serial
        self.frame_cb = frame_cb
        self.on_end = on_end
        self.preview_side = preview_side
        self.stop_ev = threading.Event()
        self.thread = None
        self.error = None

    def start(self):
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def stop(self):
        self.stop_ev.set()

    def _run(self):
        cam = None
        try:
            cam, dev = _open_camera(self.serial)
            fmt = choose_pixel_format(cam)
            use_full_resolution(cam)
            try:
                cam.TriggerMode.SetValue("Off")
            except Exception:
                pass
            try:
                cam.ExposureAuto.SetValue("Once")
            except Exception:
                pass
            fps = 0.0
            last = time.time()
            while not self.stop_ev.is_set():
                try:
                    img = cam.GrabOne(1500)
                except Exception:
                    continue  # mot frame rung, bo qua
                if not img.IsValid():
                    continue
                arr, fmt_name = image_to_array(img, fmt)
                k = max(1, -(-max(arr.shape[1], arr.shape[0])
                             // self.preview_side))
                prev = np.ascontiguousarray(arr[::k, ::k])
                png = make_png_from_np(prev)
                now = time.time()
                fps = 0.8 * fps + 0.2 * (1.0 / max(now - last, 1e-3))
                last = now
                self.frame_cb(base64.b64encode(png).decode(), {
                    "mean": float(arr.mean()), "std": float(arr.std()),
                    "fps": fps, "fmt": fmt_name,
                    "w": arr.shape[1], "h": arr.shape[0],
                    "color": arr.ndim == 3,
                })
        except Exception as e:
            self.error = str(e)
        finally:
            if cam is not None:
                try:
                    cam.StopGrabbing()
                except Exception:
                    pass
                try:
                    cam.Close()
                except Exception:
                    pass
            if self.on_end:
                self.on_end(self.error)
