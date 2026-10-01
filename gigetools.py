"""GigE Vision tools: discovery, FORCEIP (tam thoi) va dat IP vinh vien.

Dat IP vinh vien = ghi vao cac thanh ghi bootstrap cua camera (qua GVCP):
    0x00000020  Persistent IP address
    0x00000024  Persistent subnet mask
    0x00000028  Persistent default gateway
    0x00000054  Persistent IP address request
                    0x0 = khởi động thẳng vào IP tĩnh (tắt DHCP/LLA/force)
                    0x3 = thừa nhận DHCP->LLA, IP tĩnh làm dự phòng
Cac thanh ghi nay ton tai qua lan tat nguon (non-volatile).
"""

import contextlib
import random
import re
import select
import socket
import struct
import threading
import time

GVCP_PORT = 3956
GVCP_MULTICAST = "224.0.0.112"
GVCP_KEY = 0x42
CMD_DISCOVERY = 0x0002
CMD_FORCEIP = 0x0004
CMD_READREG = 0x0080
CMD_WRITEREG = 0x0082
CMD_ACK = 0x0003
CMD_PENDING_ACK = 0x0089
STATUS_SUCCESS = 0x0000
STATUS_NAMES = {
    0x0000: "SUCCESS",
    0x8002: "INVALID_PARAMETER",
    0x8003: "INVALID_ADDRESS",
    0x8006: "ACCESS_DENIED (camera đang bị app khác giữ — đóng pylon Viewer lại)",
    0x8007: "BUSY",
    0x8FFF: "GENERIC_ERROR",
}

REG_MAC_HIGH = 0x00000008
REG_MAC_LOW = 0x0000000C
REG_SUPPORTED_IP_CONFIG = 0x00000010
REG_CURRENT_IP_CONFIG = 0x00000014
REG_PERSISTENT_IP = 0x00000020
REG_PERSISTENT_MASK = 0x00000024
REG_PERSISTENT_GW = 0x00000028
REG_PERSISTENT_IP_REQUEST = 0x00000054
REG_CCP = 0x000000D0

IPV4_RE = re.compile(r"^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})$")


class GVCPError(Exception):
    def __init__(self, message, status=0):
        self.status = status
        name = STATUS_NAMES.get(status, f"UNKNOWN_0x{status:04X}")
        super().__init__(f"{message} [{name}]")


def is_ipv4(text):
    m = IPV4_RE.match(text.strip())
    return bool(m) and all(0 <= int(g) <= 255 for g in m.groups())


def ip_to_int(text):
    return struct.unpack("!I", socket.inet_aton(text))[0]


def int_to_ip(value):
    return socket.inet_ntoa(struct.pack("!I", value & 0xFFFFFFFF))


def clean_text(data):
    return data.split(b"\x00", 1)[0].decode("utf-8", errors="ignore").strip()


# ---------------------------------------------------------------- discovery


def parse_discovery_ack(data, src_ip):
    if len(data) < 0xF8:
        return None
    status, ack = struct.unpack_from("!HH", data, 0)
    if status != 0 or ack != CMD_ACK:
        return None

    def s(off, size):
        return clean_text(data[off:off + size])

    mac_raw = data[0x12:0x18]
    mac = ":".join(f"{b:02X}" for b in mac_raw)
    if mac_raw == b"\x00" * 6:
        mac = src_ip
    ip = socket.inet_ntoa(data[0x1C:0x20])
    subnet = socket.inet_ntoa(data[0x20:0x24])
    gateway = socket.inet_ntoa(data[0x24:0x28])
    if ip == "0.0.0.0" or subnet == "0.0.0.0":
        ip = src_ip

    manufacturer = s(0x38, 32)
    shift = 24 if not manufacturer and s(0x38 + 24, 32) else 0

    return {
        "source_ip": src_ip,
        "manufacturer": s(0x38 + shift, 32),
        "model": s(0x58 + shift, 32),
        "firmware": s(0x78 + shift, 32),
        "manufacturer_info": s(0x98 + shift, 48),
        "serial": s(0xC8 + shift, 16),
        "username": s(0xD8 + shift, 16),
        "mac": mac,
        "ip": ip,
        "subnet": subnet,
        "gateway": gateway,
    }


def get_local_interfaces():
    try:
        import psutil
    except ImportError:
        return None
    result = []
    for name, addrs in psutil.net_if_addrs().items():
        for a in addrs:
            if a.family == socket.AF_INET and a.address not in ("127.0.0.1", "0.0.0.0"):
                bcast = a.broadcast
                if not bcast and a.netmask:
                    ip_i = ip_to_int(a.address)
                    mask_i = ip_to_int(a.netmask)
                    bcast = int_to_ip(ip_i | (~mask_i & 0xFFFFFFFF))
                result.append((a.address, a.netmask or "255.255.255.0", bcast))
    return result


def build_discovery_packet():
    return struct.pack("!BBHHH", GVCP_KEY, 0x11, CMD_DISCOVERY, 0, 0xFFFF)


def build_forceip_packet(mac_str, ip, mask, gateway="0.0.0.0"):
    mac_bytes = bytes.fromhex(mac_str.replace(":", "").replace("-", ""))
    payload = bytearray(56)
    payload[2:8] = mac_bytes
    payload[20:24] = socket.inet_aton(ip)
    payload[36:40] = socket.inet_aton(mask)
    payload[52:56] = socket.inet_aton(gateway)
    header = struct.pack("!BBHHH", GVCP_KEY, 0x11, CMD_FORCEIP, len(payload), 1)
    return header + bytes(payload)


def discover(timeout=3.0, progress=None):
    interfaces = get_local_interfaces()
    packet = build_discovery_packet()
    socks, sock_ip = [], {}

    recv_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    recv_sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    recv_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    with contextlib.suppress(OSError):
        recv_sock.bind(("", GVCP_PORT))
    recv_sock.settimeout(0)
    socks.append(recv_sock)
    sock_ip[recv_sock.fileno()] = ""
    by_fd = {s.fileno(): s for s in socks}

    if interfaces:
        for iface_ip, _mask, _bcast in interfaces:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            try:
                s.bind((iface_ip, 0))
                s.settimeout(0)
                socks.append(s)
                sock_ip[s.fileno()] = iface_ip
                by_fd[s.fileno()] = s
            except OSError:
                s.close()

    def send_round():
        for s in socks:
            iface = sock_ip.get(s.fileno(), "")
            dests = ["255.255.255.255"]
            if iface:
                b = next((b for i, _m, b in (interfaces or []) if i == iface), None)
                if b:
                    dests.insert(0, b)
                try:
                    s.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_IF,
                                 socket.inet_aton(iface))
                    s.sendto(packet, (GVCP_MULTICAST, GVCP_PORT))
                except OSError:
                    pass
            for d in dests:
                with contextlib.suppress(OSError):
                    s.sendto(packet, (d, GVCP_PORT))
        if progress:
            progress(f"Đã gửi Discovery qua {len(socks)} socket "
                     f"({len(interfaces or [])} card mạng + multicast {GVCP_MULTICAST})")

    cameras, seen = [], set()
    deadline = time.time() + timeout
    last_send = 0.0
    while time.time() < deadline:
        if time.time() - last_send >= 1.0:
            send_round()
            last_send = time.time()
        remaining = max(0.05, deadline - time.time())
        readable, _, _ = select.select(socks, [], [], min(0.2, remaining))
        for _fd in [s.fileno() for s in readable]:
            s = by_fd.get(_fd)
            if not s:
                continue
            try:
                data, addr = s.recvfrom(4096)
            except OSError:
                continue
            cam = parse_discovery_ack(data, addr[0])
            if cam and cam["ip"] not in seen:
                seen.add(cam["ip"])
                cam["interface_ip"] = sock_ip.get(_fd, "")
                cameras.append(cam)
                if progress:
                    progress(f"Tìm thấy: {cam['manufacturer']} {cam['model']} "
                             f"(S/N {cam['serial']}) @ {cam['ip']}")

    for s in socks:
        s.close()
    return cameras


def send_forceip(mac_str, ip, mask, gateway="0.0.0.0", progress=None):
    packet = build_forceip_packet(mac_str, ip, mask, gateway)
    n = 0
    for iface_ip, _mask, _bcast in get_local_interfaces() or []:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        try:
            s.bind((iface_ip, 0))
            for dest in ("255.255.255.255", GVCP_MULTICAST):
                with contextlib.suppress(OSError):
                    s.sendto(packet, (dest, GVCP_PORT))
            n += 1
        except OSError:
            pass
        finally:
            s.close()
    if progress:
        progress(f"Đã gửi FORCEIP {mac_str} -> {ip} qua {n} card mạng")
    return n


# ---------------------------------------------------------------- GVCP client


class CameraClient:
    """GVCP client: doc/ghi bootstrap registers, giu Control Channel
    Privilege (CCP) + heartbeat trong thoi gian thao tac."""

    def __init__(self, camera_ip, local_ip=None):
        self.camera_ip = camera_ip
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind((local_ip or "", 0))
        self.sock.settimeout(0.6)
        self._req_id = 0
        self._lock = threading.Lock()
        self._ccp_magic = None
        self._hb_stop = None
        self._hb_thread = None

    def close(self):
        self.release_ccp()
        with contextlib.suppress(OSError):
            self.sock.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def _next_id(self):
        self._req_id = (self._req_id + 1) & 0xFFFF
        return self._req_id or 1

    def _cmd(self, cmd, payload=b"", retries=3):
        req_id = self._next_id()
        header = struct.pack("!BBHHH", GVCP_KEY, 0x01, cmd, len(payload), req_id)
        hard_deadline = time.monotonic() + 15.0
        last_err = None
        for _ in range(retries):
            try:
                self.sock.sendto(header + payload, (self.camera_ip, GVCP_PORT))
            except OSError as e:
                last_err = e
                continue
            deadline = time.monotonic() + 0.6
            while time.monotonic() < deadline:
                rem = deadline - time.monotonic()
                if rem <= 0:
                    break
                self.sock.settimeout(min(rem, 0.3))
                try:
                    data, _ = self.sock.recvfrom(8192)
                except (TimeoutError, socket.timeout):
                    break
                except OSError as e:
                    last_err = e
                    break
                if len(data) < 8:
                    continue
                status, ack_cmd, _plen, ack_id = struct.unpack_from("!HHHH", data, 0)
                if ack_cmd == CMD_PENDING_ACK and ack_id == req_id and len(data) >= 12:
                    ms = struct.unpack_from("!I", data, 8)[0]
                    deadline = min(time.monotonic() + ms / 1000.0, hard_deadline)
                    continue
                if ack_id != req_id:
                    continue
                if status != STATUS_SUCCESS:
                    raise GVCPError(f"Lệnh 0x{cmd:04X} bị camera từ chối", status)
                return data
        raise GVCPError(
            f"Không có phản hồi từ {self.camera_ip} "
            f"(kiểm tra kết nối / camera có đang bật không)",
            getattr(last_err, "status", 0) if isinstance(last_err, GVCPError) else 0,
        )

    def read_reg(self, addr):
        with self._lock:
            data = self._cmd(CMD_READREG, struct.pack("!I", addr))
            return struct.unpack_from("!I", data, 8)[0]

    def write_reg(self, addr, value):
        with self._lock:
            self._cmd(CMD_WRITEREG, struct.pack("!II", addr, value & 0xFFFFFFFF))

    # --- Control Channel Privilege ---

    def acquire_ccp(self):
        if self._ccp_magic is not None:
            return
        magic = random.randint(1, 0xFFFFFFFF)
        self.write_reg(REG_CCP, magic)
        got = self.read_reg(REG_CCP)
        if got != magic:
            raise GVCPError("Không lấy được quyền điều khiển (CCP)", 0x8007)
        self._ccp_magic = magic
        self._hb_stop = threading.Event()

        def hb():
            while not self._hb_stop.wait(1.5):
                try:
                    if self.read_reg(REG_CCP) != magic:
                        break
                except (GVCPError, OSError):
                    break

        self._hb_thread = threading.Thread(target=hb, daemon=True)
        self._hb_thread.start()

    def release_ccp(self):
        if self._ccp_magic is None:
            return
        if self._hb_stop:
            self._hb_stop.set()
        if self._hb_thread:
            self._hb_thread.join(timeout=2.0)
        with contextlib.suppress(GVCPError, OSError):
            self.write_reg(REG_CCP, 0)
        self._ccp_magic = None

    # --- thong tin ---

    def read_bootstrap_table(self):
        """Doc toan bo bootstrap register lien quan IP, tra ve danh sach
        (addr, name, raw, decoded, status) de hien bang trong GUI."""
        names = {
            0x00000000: "GVCPConfiguration",
            REG_SUPPORTED_IP_CONFIG: "SupportedIPConfig",
            REG_CURRENT_IP_CONFIG: "CurrentIPConfig",
            REG_PERSISTENT_IP: "PersistentIPAddress",
            REG_PERSISTENT_MASK: "PersistentSubnetMask",
            REG_PERSISTENT_GW: "PersistentDefaultGateway",
            REG_PERSISTENT_IP_REQUEST: "PersistentIPRequest",
        }
        mode_names = {1: "DHCP", 2: "LLA", 4: "ForceIP"}
        ip_cfg = {REG_SUPPORTED_IP_CONFIG, REG_CURRENT_IP_CONFIG}
        rows = []
        for addr in sorted(names):
            name = names[addr]
            try:
                raw = self.read_reg(addr)
            except GVCPError as e:
                rows.append((addr, name, None, str(e), "err"))
                continue
            if addr == 0x00000000:
                dec = f"GV Spec {(raw >> 16) & 0xFFFF}.{raw & 0xFFFF} | big-endian"
            elif addr in ip_cfg:
                flags = "|".join(n for b, n in mode_names.items() if raw & b)
                dec = f"{raw:08b}"[-3:][::-1] + " -> " + (flags or "STATIC only")
            elif addr == REG_PERSISTENT_IP_REQUEST:
                dec = {0: "0: vao tinh (tat DHCP/LLA)",
                       3: "3: DHCP->LLA, tinh du phong"}.get(raw, str(raw))
            else:
                dec = int_to_ip(raw)
            rows.append((addr, name, raw, dec, "ok"))
        return rows

    def get_bootstrap_info(self):
        info = {}
        spec = self.read_reg(0x00000000)
        info["spec_version"] = f"{(spec >> 16) & 0xFFFF}.{spec & 0xFFFF}"
        mac_h = self.read_reg(REG_MAC_HIGH) & 0xFFFF
        mac_l = self.read_reg(REG_MAC_LOW)
        info["mac"] = f"{mac_h >> 8:02X}:{mac_h & 0xFF:02X}:" \
                      f"{(mac_l >> 24) & 0xFF:02X}:{(mac_l >> 16) & 0xFF:02X}:" \
                      f"{(mac_l >> 8) & 0xFF:02X}:{mac_l & 0xFF:02X}"
        sup = self.read_reg(REG_SUPPORTED_IP_CONFIG)
        cur = self.read_reg(REG_CURRENT_IP_CONFIG)
        names = {1: "DHCP", 2: "LLA", 4: "ForceIP"}
        flags = lambda v: ", ".join(n for b, n in names.items() if v & b) or "Tĩnh"
        info["supported"] = flags(sup)
        info["current_mode"] = flags(cur)
        return info

    # --- dat IP vinh vien ---

    def get_persistent(self):
        return {
            "ip": int_to_ip(self.read_reg(REG_PERSISTENT_IP)),
            "mask": int_to_ip(self.read_reg(REG_PERSISTENT_MASK)),
            "gw": int_to_ip(self.read_reg(REG_PERSISTENT_GW)),
            "request": self.read_reg(REG_PERSISTENT_IP_REQUEST),
        }

    def set_persistent_ip(self, ip, mask, gw="0.0.0.0", absolute_static=True,
                          progress=None):
        """Ghi IP tĩnh non-volatile. absolute_static=True -> tat DHCP/LLA,
        camera khởi động thẳng vào IP tĩnh. False -> request=0x3,
        DHCP/LLA trước, IP tĩnh làm dự phòng."""
        request = 0x00000000 if absolute_static else 0x00000003
        self.acquire_ccp()
        try:
            old = self.get_persistent()
            if progress:
                progress(f"IP tĩnh cũ: {old['ip']} / {old['mask']} / {old['gw']} "
                         f"(request=0x{old['request']:08X})")
            self.write_reg(REG_PERSISTENT_IP, ip_to_int(ip))
            self.write_reg(REG_PERSISTENT_MASK, ip_to_int(mask))
            self.write_reg(REG_PERSISTENT_GW, ip_to_int(gw))
            self.write_reg(REG_PERSISTENT_IP_REQUEST, request)
            new = self.get_persistent()
            if (new["ip"] != ip or new["mask"] != mask
                    or new["gw"] != gw or new["request"] != request):
                raise GVCPError(
                    f"Ghi xong nhung doc lai khong khop "
                    f"({new['ip']}/{new['mask']}/0x{new['request']:X})")
            if progress:
                mode = ("khởi động thẳng vào IP tĩnh" if absolute_static
                        else "DHCP/LLA trước, IP tĩnh làm dự phòng")
                progress(f"XÁC NHẬN: IP tĩnh = {new['ip']} / {new['mask']} / "
                         f"{new['gw']} ({mode}) — lưu qua lần tắt nguồn")
            return new
        finally:
            self.release_ccp()
