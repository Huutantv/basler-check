import sys

import gigetools as gt


def usage():
    print("""GigE Vision IP tools

  python main.py                                  : quen tim camera
  python main.py probe <IP>                       : do truc tiep 1 IP
  python main.py forceip <MAC> <IP> [mask]        : gan IP TAM THOI (mat nguon tro ve cu)
  python main.py setip <IP camera> <IP moi> [mask] [gw] [--fallback]
                                                  : dat IP VINH VIEN (ton qua tat nguon)
      --fallback: giu DHCP/LLA, IP tinh lam du phong
      khong co --fallback: tat DHCP/LLA, khoi dong thang vao IP tinh""")


def show(cam):
    print("=" * 50)
    print(f"Manufacturer : {cam['manufacturer']}")
    print(f"Model        : {cam['model']}")
    print(f"Serial       : {cam['serial']}")
    print(f"MAC          : {cam['mac']}")
    print(f"IP           : {cam['ip']}")
    print(f"Subnet       : {cam['subnet']}")
    print(f"Gateway      : {cam['gateway']}")
    print(f"Firmware     : {cam['firmware']}")
    print("=" * 50)


def do_scan():
    print("Dang tim camera...")
    cams = gt.discover(progress=lambda m: print(" ", m))
    if not cams:
        print("[X] Khong tim thay camera (kiem tra nguon, day LAN, pylon dong chua)")
    else:
        print(f"[OK] Tim thay {len(cams)} camera")
        for cam in cams:
            show(cam)
    return cams


def do_probe(ip):
    import socket, struct
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.settimeout(2)
    pkt = gt.build_discovery_packet()
    for _ in range(2):
        try:
            s.sendto(pkt, (ip, gt.GVCP_PORT))
            data, addr = s.recvfrom(4096)
            cam = gt.parse_discovery_ack(data, addr[0])
            if cam:
                print(f"Probe {ip}: OK")
                show(cam)
                s.close()
                return
        except OSError:
            pass
    s.close()
    print(f"Probe {ip}: khong phan ung")


def do_forceip(mac, ip, mask="255.255.0.0"):
    if not gt.is_ipv4(ip) or not gt.is_ipv4(mask):
        print("IP/mask khong hop le"); return
    gt.send_forceip(mac, ip, mask, progress=lambda m: print(m))
    print("Cho ~3 giay roi chay python main.py de tim lai")


def do_setip(cam_ip, ip, mask="255.255.0.0", gw="0.0.0.0", absolute=True):
    for v in (cam_ip, ip, mask, gw):
        if not gt.is_ipv4(v):
            print(f"IP khong hop le: {v}"); return
    with gt.CameraClient(cam_ip) as c:
        info = c.get_bootstrap_info()
        print(f"Camera {info['mac']} | GV spec {info['spec_version']} | "
              f"hien tai: {info['current_mode']} | ho tro: {info['supported']}")
        print(f"Dang ghi IP vinh vien: {ip} / {mask} / {gw}")
        c.set_persistent_ip(ip, mask, gw, absolute_static=absolute,
                            progress=lambda m: print(" ", m))
    print("Da xong. Camera van giu IP hien tai den lan tat nguon ke tiep.")
    if ip != cam_ip:
        print(f"(muon AP DUNG NGAY o {ip}: python main.py forceip <MAC> {ip} {mask})")


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(errors="replace")
    except Exception:
        pass

    args = sys.argv[1:]
    try:
        if not args:
            do_scan()
        elif args[0] == "probe" and len(args) >= 2:
            do_probe(args[1])
        elif args[0] == "forceip" and len(args) >= 3:
            do_forceip(args[1], args[2], args[3] if len(args) > 3 else "255.255.0.0")
        elif args[0] == "setip" and len(args) >= 3:
            rest = [a for a in args[3:] if not a.startswith("--")]
            absolute = "--fallback" not in args
            do_setip(args[1], args[2],
                     rest[0] if rest else "255.255.0.0",
                     rest[1] if len(rest) > 1 else "0.0.0.0",
                     absolute)
        else:
            usage()
    except gt.GVCPError as e:
        print(f"[X] {e}")
    except KeyboardInterrupt:
        pass

    if not args:
        input("\nNhan Enter de thoat...")
