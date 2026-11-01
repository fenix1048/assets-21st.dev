"""
import ctypes
import json
import math
import os
import queue
import re
import struct
import subprocess
import sys
import threading
import time
import tkinter as tk
import urllib.request
import winreg
from ctypes import wintypes as w
from tkinter import messagebox, ttk

# ------------------------- réglages -------------------------
MIN_STEP_MM = 0.2          # ignore les micro-tremblements (en mm)
APP_NAME = "TouchpadDistance"
DATA_DIR = os.path.join(os.environ.get("APPDATA", os.path.dirname(os.path.abspath(__file__))), APP_NAME)
CFG_FILE = os.path.join(DATA_DIR, "config.json")
OLD_CALIB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "touchpad_calib.json")
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"

# --- mises à jour (silencieuses) ---
VERSION = "1.0.0"
UPDATE_URL = "https://raw.githubusercontent.com/fenix1042/assets-21st.dev/main/TrackPadKm.pyw"

DEFAULTS = { "unit": "Auto", "count_move": True, "count_drag": True, "count_scroll": False,
             "total_cm": 0.0, "today_cm": 0.0, "day": " ", "calib": None}
UNITS = { "mm": 10.0, "cm": 1.0, "m": 0.01, "km": 1e-5, "pouces": 1 / 2.54, "pieds": 1 / 30.48, "miles": 1 / 160934.4}
SHORT = { "pouces": "in", "pieds": "ft", "miles": "mi" }

# couleurs
BG, CARD, FIELD = "#12141c", "#1b1f2b", "#2a3042"
FG, MUTED = "#e8ecf4", "#8b93a7"
ACCENT, GREEN, ORANGE = "#5b8cff", "#3ddc97", "#ffb454"

# ------------------------- config -------------------------
def load_cfg():
    cfg = dict(DEFAULTS)
    try:
        with open(CFG_FILE, "r", encoding="utf-8") as f:
            cfg.update(json.load(f))
    except Exception:
        try:
            with open(OLD_CALIB, "r", encoding="utf-8") as f:
                d = json.load(f)
                cfg["calib"] = [float(d["ux"]), float(d["uy"])]
        except Exception:
            pass
    return cfg

CFG = load_cfg()

def save_cfg():
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        tmp = CFG_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(CFG, f)
        os.replace(tmp, CFG_FILE)
    except OSError:
        pass

def set_startup(on):
    try:
        key = winreg.CreateKey(winreg.HKEY_CURRENT_USER, RUN_KEY)
        if on:
            exe = sys.executable
            pyw = os.path.join(os.path.dirname(exe), "pythonw.exe")
            if os.path.exists(pyw):
                exe = pyw
            cmd = f'"{exe}" "{os.path.abspath(__file__)}" --hidden'
            winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, cmd)
        else:
            try:
                winreg.DeleteValue(key, APP_NAME)
            except FileNotFoundError:
                pass
        winreg.CloseKey(key)
    except OSError:
        pass

def convert(cm, unit):
    if unit == "Auto":
        unit = "cm" if cm < 100 else ("m" if cm < 100000 else "km")
    return cm * UNITS[unit], SHORT.get(unit, unit)

def fmt(v):
    if v >= 1000:
        return f"{v:,.0f}".replace(",", " ")
    if v >= 100:
        return f"{v:.1f}"
    if v >= 10:
        return f"{v:.2f}"
    return f"{v:.3f}"

# ------------------------- mises à jour (100% silencieuses) -------------------------
UPQ = queue.Queue()
RESTART = False
RESTART_HIDDEN = False
MUTEX = None

def ver_tuple(s):
    try:
        return tuple(int(x) for x in s.strip().split("."))
    except ValueError:
        return (0,)

def pyw_exe():
    exe = sys.executable
    pyw = os.path.join(os.path.dirname(exe), "pythonw.exe")
    return pyw if os.path.exists(pyw) else exe

def fetch_update():
    if not UPDATE_URL.startswith("https://"):
        return None
    req = urllib.request.Request(UPDATE_URL, headers={"User-Agent": APP_NAME})
    with urllib.request.urlopen(req, timeout=10) as r:
        if not r.geturl().startswith("https://"):
            return None
        data = r.read(2_000_001)
        if len(data) > 2_000_000:
            return None
        src = data.decode("utf-8")
        m = re.search(r'^VERSION\s*=\s*"([^"]+)"', src, re.M)
        if not m or ver_tuple(m.group(1)) <= ver_tuple(VERSION):
            return None
        compile(src, "update", "exec")
        return m.group(1), data

def check_updates():
    def run():
        try:
            r = fetch_update()
            if r:
                UPQ.put(("found", r))
        except Exception:
            pass  # échec silencieux
    threading.Thread(target=run, daemon=True).start()

def install_update(info):
    def run():
        try:
            version, data = info
            me = os.path.abspath(__file__)
            tmp = me + ".new"
            with open(tmp, "wb") as f:
                f.write(data)
            try:
                with open(me, "rb") as f, open(me + ".bak", "wb") as b:
                    b.write(f.read())
            except OSError:
                pass
            os.replace(tmp, me)
            UPQ.put(("installed", version))
        except Exception:
            pass  # échec silencieux
    threading.Thread(target=run, daemon=True).start()

# ------------------------- API Windows -------------------------
user32 = ctypes.WinDLL("user32")
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
hid = ctypes.WinDLL("hid")
shell32 = ctypes.WinDLL("shell32")

LRESULT = ctypes.c_ssize_t
WNDPROC = ctypes.WINFUNCTYPE(LRESULT, w.HWND, w.UINT, w.WPARAM, w.LPARAM)
WM_TRAY = 0x8001

class WNDCLASSW(ctypes.Structure):
    _fields_ = [("style", w.UINT), ("lpfnWndProc", WNDPROC), ("cbClsExtra", ctypes.c_int),
                ("cbWndExtra", ctypes.c_int), ("hInstance", w.HINSTANCE), ("hIcon", w.HANDLE),
                ("hCursor", w.HANDLE), ("hbrBackground", w.HANDLE), ("lpszMenuName", w.LPCWSTR),
                ("lpszClassName", w.LPCWSTR)]

class RAWINPUTDEVICE(ctypes.Structure):
    _fields_ = [("usUsagePage", w.USHORT), ("usUsage", w.USHORT), ("dwFlags", w.DWORD), ("hwndTarget", w.HWND)]

class RAWINPUTHEADER(ctypes.Structure):
    _fields_ = [("dwType", w.DWORD), ("dwSize", w.DWORD), ("hDevice", w.HANDLE), ("wParam", w.WPARAM)]

class NOTIFYICONDATAW(ctypes.Structure):
    _fields_ = [("cbSize", w.DWORD), ("hWnd", w.HWND), ("uID", w.UINT), ("uFlags", w.UINT),
                ("uCallbackMessage", w.UINT), ("hIcon", w.HICON), ("szTip", w.WCHAR * 128),
                ("dwState", w.DWORD), ("dwStateMask", w.DWORD), ("szInfo", w.WCHAR * 256),
                ("uTimeout", w.UINT), ("szInfoTitle", w.WCHAR * 64), ("dwInfoFlags", w.DWORD),
                ("guidItem", ctypes.c_ubyte * 16), ("hBalloonIcon", w.HICON)]

class HIDP_CAPS(ctypes.Structure):
    _fields_ = [("Usage", ctypes.c_ushort), ("UsagePage", ctypes.c_ushort),
                ("InputReportByteLength", ctypes.c_ushort), ("OutputReportByteLength", ctypes.c_ushort),
                ("FeatureReportByteLength", ctypes.c_ushort), ("Reserved", ctypes.c_ushort * 17),
                ("NumberLinkCollectionNodes", ctypes.c_ushort), ("NumberInputButtonCaps", ctypes.c_ushort),
                ("NumberInputValueCaps", ctypes.c_ushort), ("NumberInputDataIndices", ctypes.c_ushort),
                ("NumberOutputButtonCaps", ctypes.c_ushort), ("NumberOutputValueCaps", ctypes.c_ushort),
                ("NumberOutputDataIndices", ctypes.c_ushort), ("NumberFeatureButtonCaps", ctypes.c_ushort),
                ("NumberFeatureValueCaps", ctypes.c_ushort), ("NumberFeatureDataIndices", ctypes.c_ushort)]

class VCAPS(ctypes.Structure):
    _fields_ = [("UsagePage", ctypes.c_ushort), ("ReportID", ctypes.c_ubyte), ("IsAlias", ctypes.c_ubyte),
                ("BitField", ctypes.c_ushort), ("LinkCollection", ctypes.c_ushort),
                ("LinkUsage", ctypes.c_ushort), ("LinkUsagePage", ctypes.c_ushort),
                ("IsRange", ctypes.c_ubyte), ("IsStringRange", ctypes.c_ubyte),
                ("IsDesignatorRange", ctypes.c_ubyte), ("IsAbsolute", ctypes.c_ubyte),
                ("HasNull", ctypes.c_ubyte), ("Reserved", ctypes.c_ubyte),
                ("BitSize", ctypes.c_ushort), ("ReportCount", ctypes.c_ushort),
                ("Reserved2", ctypes.c_ushort * 5), ("UnitsExp", w.ULONG), ("Units", w.ULONG),
                ("LogicalMin", ctypes.c_long), ("LogicalMax", ctypes.c_long),
                ("PhysicalMin", ctypes.c_long), ("PhysicalMax", ctypes.c_long),
                ("Data", ctypes.c_ushort * 8)]

user32.DefWindowProcW.argtypes = [w.HWND, w.UINT, w.WPARAM, w.LPARAM]
user32.DefWindowProcW.restype = LRESULT
user32.RegisterClassW.argtypes = [ctypes.POINTER(WNDCLASSW)]
user32.RegisterClassW.restype = w.ATOM
user32.CreateWindowExW.argtypes = [w.DWORD, w.LPCWSTR, w.LPCWSTR, w.DWORD, ctypes.c_int, ctypes.c_int,
                                   ctypes.c_int, ctypes.c_int, w.HWND, w.HMENU, w.HINSTANCE, w.LPVOID]
user32.CreateWindowExW.restype = w.HWND
user32.RegisterRawInputDevices.argtypes = [ctypes.POINTER(RAWINPUTDEVICE), w.UINT, w.UINT]
user32.RegisterRawInputDevices.restype = w.BOOL
user32.GetRawInputData.argtypes = [ctypes.c_void_p, w.UINT, ctypes.c_void_p, ctypes.POINTER(w.UINT), w.UINT]
user32.GetRawInputData.restype = w.UINT
user32.GetRawInputDeviceInfoW.argtypes = [ctypes.c_void_p, w.UINT, ctypes.c_void_p, ctypes.POINTER(w.UINT)]
user32.GetRawInputDeviceInfoW.restype = w.UINT
user32.GetMessageW.argtypes = [ctypes.POINTER(w.MSG), w.HWND, w.UINT, w.UINT]
user32.TranslateMessage.argtypes = [ctypes.POINTER(w.MSG)]
user32.DispatchMessageW.argtypes = [ctypes.POINTER(w.MSG)]
user32.GetAsyncKeyState.argtypes = [ctypes.c_int]
user32.GetAsyncKeyState.restype = ctypes.c_short
user32.GetParent.argtypes = [w.HWND]
user32.GetParent.restype = w.HWND
user32.GetWindowLongW.argtypes = [w.HWND, ctypes.c_int]
user32.GetWindowLongW.restype = ctypes.c_long
user32.SetWindowLongW.argtypes = [w.HWND, ctypes.c_int, ctypes.c_long]
user32.SetWindowLongW.restype = ctypes.c_long
user32.RegisterWindowMessageW.argtypes = [w.LPCWSTR]
user32.RegisterWindowMessageW.restype = w.UINT
user32.CreatePopupMenu.restype = w.HMENU
user32.AppendMenuW.argtypes = [w.HMENU, w.UINT, ctypes.c_size_t, w.LPCWSTR]
user32.AppendMenuW.restype = w.BOOL
user32.TrackPopupMenu.argtypes = [w.HMENU, w.UINT, ctypes.c_int, ctypes.c_int, ctypes.c_int, w.HWND, ctypes.c_void_p]
user32.TrackPopupMenu.restype = ctypes.c_int
user32.DestroyMenu.argtypes = [w.HMENU]
user32.GetCursorPos.argtypes = [ctypes.POINTER(w.POINT)]
user32.SetForegroundWindow.argtypes = [w.HWND]
user32.PostMessageW.argtypes = [w.HWND, w.UINT, w.WPARAM, w.LPARAM]
user32.CreateIcon.argtypes = [w.HINSTANCE, ctypes.c_int, ctypes.c_int, w.BYTE, w.BYTE, ctypes.c_char_p, ctypes.c_char_p]
user32.CreateIcon.restype = w.HICON
kernel32.GetModuleHandleW.argtypes = [w.LPCWSTR]
kernel32.GetModuleHandleW.restype = w.HMODULE
kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, w.BOOL, w.LPCWSTR]
kernel32.CreateMutexW.restype = w.HANDLE
kernel32.CloseHandle.argtypes = [w.HANDLE]
kernel32.CloseHandle.restype = w.BOOL
shell32.Shell_NotifyIconW.argtypes = [w.DWORD, ctypes.POINTER(NOTIFYICONDATAW)]
shell32.Shell_NotifyIconW.restype = w.BOOL
hid.HidP_GetCaps.argtypes = [ctypes.c_void_p, ctypes.POINTER(HIDP_CAPS)]
hid.HidP_GetValueCaps.argtypes = [ctypes.c_int, ctypes.POINTER(VCAPS), ctypes.POINTER(ctypes.c_ushort), ctypes.c_void_p]
hid.HidP_GetUsageValue.argtypes = [ctypes.c_int, ctypes.c_ushort, ctypes.c_ushort, ctypes.c_ushort,
                                   ctypes.POINTER(w.ULONG), ctypes.c_void_p, ctypes.c_char_p, w.ULONG]
hid.HidP_GetUsages.argtypes = [ctypes.c_int, ctypes.c_ushort, ctypes.c_ushort, ctypes.POINTER(ctypes.c_ushort),
                               ctypes.POINTER(w.ULONG), ctypes.c_void_p, ctypes.c_char_p, w.ULONG]

for _f in (hid.HidP_GetCaps, hid.HidP_GetValueCaps, hid.HidP_GetUsageValue, hid.HidP_GetUsages):
    _f.restype = ctypes.c_long

HID_OK = 0x00110000

def phys_cm(c):
    rng = abs(c.PhysicalMax - c.PhysicalMin)
    e = c.UnitsExp & 0xF
    if e >= 8:
        e -= 16
    f = {0x11: 1.0, 0x13: 2.54}.get(c.Units & 0xFF, 0.0)
    return rng * (10 ** e) * f

# ------------------------- icône -------------------------
def icon_pixels(n=32):
    rows = []
    r, m = 7.0, 2.0
    half = n / 2.0
    inner = half - m - r
    for y in range(n):
        row = []
        for x in range(n):
            px, py = x + 0.5, y + 0.5
            dx = max(abs(px - half) - inner, 0.0)
            dy = max(abs(py - half) - inner, 0.0)
            cov = max(0.0, min(1.0, r + 0.5 - math.hypot(dx, dy)))
            yc = half + 5.5 * math.sin((px / n) * math.pi * 2.2 + 0.6)
            wc = max(0.0, min(1.0, 1.9 - abs(py - yc))) if 6 <= px <= n - 6 else 0.0
            col = (91 + (255 - 91) * wc, 140 + (255 - 140) * wc, 255.0)
            row.append((int(col[0]), int(col[1]), int(col[2]), int(cov * 255)))
        rows.append(row)
    return rows

def make_hicon():
    n = 32
    xor = bytearray()
    for row in icon_pixels(n):
        for (r, g, b, a) in row:
            xor += bytes((b, g, r, a))
    return user32.CreateIcon(kernel32.GetModuleHandleW(None), n, n, 1, 32, bytes(n * 4), bytes(xor))

class Tray:
    def __init__(self):
        self.nid = None
        self.icon = None
    def add(self, hwnd):
        if self.icon is None:
            self.icon = make_hicon()
        nid = NOTIFYICONDATAW()
        nid.cbSize = ctypes.sizeof(NOTIFYICONDATAW)
        nid.hWnd = hwnd
        nid.uID = 1
        nid.uFlags = 7
        nid.uCallbackMessage = WM_TRAY
        nid.hIcon = self.icon
        nid.szTip = "Touchpad Distance"
        self.nid = nid
        shell32.Shell_NotifyIconW(0, ctypes.byref(nid))
    def tip(self, text):
        if self.nid is not None:
            self.nid.szTip = text[:127]
            shell32.Shell_NotifyIconW(1, ctypes.byref(self.nid))
    def remove(self):
        if self.nid is not None:
            shell32.Shell_NotifyIconW(2, ctypes.byref(self.nid))
            self.nid = None

TRAY = Tray()
CMDS = queue.Queue()

# ------------------------- lecture du pavé -------------------------
class Device:
    def __init__(self, hdev):
        sz = w.UINT(0)
        user32.GetRawInputDeviceInfoW(hdev, 0x20000005, None, ctypes.byref(sz))
        self.pp = ctypes.create_string_buffer(sz.value)
        user32.GetRawInputDeviceInfoW(hdev, 0x20000005, self.pp, ctypes.byref(sz))
        caps = HIDP_CAPS()
        hid.HidP_GetCaps(self.pp, ctypes.byref(caps))
        n = ctypes.c_ushort(caps.NumberInputValueCaps)
        arr = (VCAPS * max(n.value, 1))()
        hid.HidP_GetValueCaps(0, arr, ctypes.byref(n), self.pp)
        fingers = {}
        for c in arr[:n.value]:
            lo = c.Data[0]
            hi = c.Data[1] if c.IsRange else lo
            d = fingers.setdefault(c.LinkCollection, {})
            if c.UsagePage == 1 and lo <= 0x30 <= hi:
                d["x"] = c
            if c.UsagePage == 1 and lo <= 0x31 <= hi:
                d["y"] = c
        self.fingers = {lc: d for lc, d in fingers.items() if "x" in d and "y" in d}
        self.ok = bool(self.fingers)
        self.rid = None
        self.auto = None
        self.rx = self.ry = 0
        if self.ok:
            d = next(iter(self.fingers.values()))
            cx, cy = d["x"], d["y"]
            self.rid = cx.ReportID
            self.rx = abs(cx.LogicalMax - cx.LogicalMin)
            self.ry = abs(cy.LogicalMax - cy.LogicalMin)
            wc, hc = phys_cm(cx), phys_cm(cy)
            if wc > 0 and hc > 0 and self.rx and self.ry:
                self.auto = (self.rx / wc, self.ry / hc)

    def read(self, rep):
        if not self.ok or not rep or rep[0] != self.rid:
            return None
        out = []
        n = len(rep)
        for lc in self.fingers:
            lst = (ctypes.c_ushort * 16)()
            ln = w.ULONG(16)
            st = hid.HidP_GetUsages(0, 0x0D, lc, lst, ctypes.byref(ln), self.pp, rep, n)
            if (st & 0xFFFFFFFF) != HID_OK or 0x42 not in lst[:ln.value]:
                continue
            v = w.ULONG(0)
            if (hid.HidP_GetUsageValue(0, 1, lc, 0x30, ctypes.byref(v), self.pp, rep, n) & 0xFFFFFFFF) != HID_OK:
                continue
            x = v.value
            if (hid.HidP_GetUsageValue(0, 1, lc, 0x31, ctypes.byref(v), self.pp, rep, n) & 0xFFFFFFFF) != HID_OK:
                continue
            y = v.value
            cid = lc
            if (hid.HidP_GetUsageValue(0, 0x0D, lc, 0x51, ctypes.byref(v), self.pp, rep, n) & 0xFFFFFFFF) == HID_OK:
                cid = v.value
            out.append((cid, x, y))
        return out

class Tracker:
    def __init__(self):
        self.paused = False
        self.cal = False
        self.ext = [1e9, -1e9, 1e9, -1e9]
        self.last = {}
        self.ux = self.uy = None
        self.auto = None
        self.rx = self.ry = 0
        self.seen = False
        self.src = "auto"
        self.session = 0.0
        self.dirty = False

    def device_ready(self, dev):
        self.seen = True
        self.auto = dev.auto
        self.rx, self.ry = dev.rx, dev.ry
        cal = CFG.get("calib")
        if cal and len(cal) == 2 and cal[0] and cal[1]:
            self.ux, self.uy = float(cal[0]), float(cal[1])
            self.src = "manuel"
        elif self.auto:
            self.ux, self.uy = self.auto
            self.src = "auto"

    def info(self):
        if not self.seen:
            return "En attente du pavé… pose un doigt dessus"
        if not self.ux:
            return "Taille du pavé inconnue → clique « Calibrer »"
        return f"Pavé {self.rx / self.ux:.1f} × {self.ry / self.uy:.1f} cm  ·  calibrage {self.src}"

    def add(self, d):
        CFG["total_cm"] += d
        CFG["today_cm"] += d
        self.session += d
        self.dirty = True

    def feed(self, pts):
        if pts is None:
            return
        if self.cal:
            for _, x, y in pts:
                e = self.ext
                e[0], e[1] = min(e[0], x), max(e[1], x)
                e[2], e[3] = min(e[2], y), max(e[3], y)
            return
        if self.paused or not self.ux or not pts:
            self.last = {}
            return
        n = len(pts)
        if user32.GetAsyncKeyState(1) & 0x8000:
            kind = "drag"
        elif n == 1:
            kind = "move"
        elif n == 2:
            kind = "scroll"
        else:
            self.last = {}
            return
        if not CFG["count_" + kind]:
            self.last = {}
            return
        new, ds, m = {}, [], 0
        for cid, x, y in pts:
            p = self.last.get(cid)
            if p is None:
                new[cid] = (x, y)
                continue
            m += 1
            d = math.hypot((x - p[0]) / self.ux, (y - p[1]) / self.uy)
            if d * 10 < MIN_STEP_MM:
                new[cid] = p
            else:
                ds.append(d)
                new[cid] = (x, y)
        self.last = new
        if ds:
            self.add(sum(ds) / m if kind == "scroll" else max(ds))

T = Tracker()

def on_input(lp, devices):
    size = w.UINT(0)
    hdr = ctypes.sizeof(RAWINPUTHEADER)
    if user32.GetRawInputData(lp, 0x10000003, None, ctypes.byref(size), hdr) != 0:
        return
    buf = ctypes.create_string_buffer(size.value)
    if user32.GetRawInputData(lp, 0x10000003, buf, ctypes.byref(size), hdr) != size.value:
        return
    h = RAWINPUTHEADER.from_buffer(buf)
    if h.dwType != 2:
        return
    size_hid, count = struct.unpack_from("<II", buf, hdr)
    base = hdr + 8
    dev = devices.get(h.hDevice)
    if dev is None:
        dev = devices[h.hDevice] = Device(h.hDevice)
    if dev.ok:
        T.device_ready(dev)
    for i in range(count):
        rep = buf.raw[base + i * size_hid: base + (i + 1) * size_hid]
        T.feed(dev.read(rep))

def tray_menu(hwnd):
    m = user32.CreatePopupMenu()
    user32.AppendMenuW(m, 0, 1, "Ouvrir")
    user32.AppendMenuW(m, 0, 2, "Reprendre" if T.paused else "Mettre en pause")
    user32.AppendMenuW(m, 0x800, 0, None)
    user32.AppendMenuW(m, 0, 3, "Quitter")
    pt = w.POINT()
    user32.GetCursorPos(ctypes.byref(pt))
    user32.SetForegroundWindow(hwnd)
    cmd = user32.TrackPopupMenu(m, 0x100 | 0x2 | 0x20, pt.x, pt.y, 0, hwnd, None)
    user32.PostMessageW(hwnd, 0, 0, 0)
    user32.DestroyMenu(m)
    if cmd == 1:
        CMDS.put("show")
    elif cmd == 2:
        CMDS.put("toggle")
    elif cmd == 3:
        CMDS.put("quit")

def raw_loop():
    devices = {}
    wm_tbc = user32.RegisterWindowMessageW("TaskbarCreated")
    def proc(hwnd, msg, wp, lp):
        if msg == 0x00FF:
            try:
                on_input(lp, devices)
            except Exception:
                pass
        elif msg == WM_TRAY:
            ev = lp & 0xFFFF
            if ev in (0x202, 0x203):
                CMDS.put("show")
            elif ev == 0x205:
                try:
                    tray_menu(hwnd)
                except Exception:
                    pass
            return 0
        elif msg == wm_tbc:
            TRAY.add(hwnd)
        return user32.DefWindowProcW(hwnd, msg, wp, lp)
    cb = WNDPROC(proc)
    wc = WNDCLASSW()
    wc.lpfnWndProc = cb
    wc.hInstance = kernel32.GetModuleHandleW(None)
    wc.lpszClassName = "TouchpadDistanceRaw"
    user32.RegisterClassW(ctypes.byref(wc))
    hwnd = user32.CreateWindowExW(0, "TouchpadDistanceRaw", "x", 0, 0, 0, 0, 0, None, None, wc.hInstance, None)
    TRAY.add(hwnd)
    rid = RAWINPUTDEVICE(0x0D, 0x05, 0x100, hwnd)
    user32.RegisterRawInputDevices(ctypes.byref(rid), 1, ctypes.sizeof(rid))
    msg = w.MSG()
    while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
        user32.TranslateMessage(ctypes.byref(msg))
        user32.DispatchMessageW(ctypes.byref(msg))

# ------------------------- interface -------------------------
def dark_titlebar(win):
    try:
        win.update_idletasks()
        hwnd = user32.GetParent(win.winfo_id()) or win.winfo_id()
        v = ctypes.c_int(1)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(ctypes.c_void_p(hwnd), 20, ctypes.byref(v), 4)
    except Exception:
        pass

class App:
    def __init__(self, hidden):
        self.root = tk.Tk()
        r = self.root
        if hidden:
            r.withdraw()  # CORRECTIF : cache la fenêtre dès le départ (plus de flash)
        r.title("Touchpad Distance")
        r.configure(bg=BG)
        r.resizable(False, False)
        r.protocol("WM_DELETE_WINDOW", self.hide)
        self.sc = r.winfo_fpixels("1i") / 96.0
        self.S = int(170 * self.sc)
        self._job = None
        self._was_down = False
        self._ui = self._save = self._tip = 0.0
        self.wiz = None

        n = 32
        img = tk.PhotoImage(width=n, height=n)
        for y, row in enumerate(icon_pixels(n)):
            for x, (rr, gg, bb, a) in enumerate(row):
                if a >= 128:
                    img.put(f"#{rr:02x}{gg:02x}{bb:02x}", (x, y))
        r.iconphoto(True, img)
        self._img = img
        self.setup_style()
        self.build()
        self.build_overlay()
        r.update_idletasks()
        r.geometry(f"{int(420 * self.sc)}x{r.winfo_reqheight()}")
        dark_titlebar(r)
        self.refresh()
        if hidden:
            r.withdraw()
        threading.Thread(target=raw_loop, daemon=True).start()
        self.tick()
        # Vérification silencieuse 15 secondes après le démarrage, puis toutes les 6h
        r.after(15000, self.auto_check)

    def setup_style(self):
        st = ttk.Style()
        st.theme_use("clam")
        st.configure("TCombobox", fieldbackground=FIELD, background=FIELD, foreground=FG, arrowcolor=FG,
                     bordercolor=FIELD, lightcolor=FIELD, darkcolor=FIELD, padding=4)
        st.map("TCombobox", fieldbackground=[("readonly", FIELD)], foreground=[("readonly", FG)],
               selectbackground=[("readonly", FIELD)], selectforeground=[("readonly", FG)])
        st.configure("Horizontal.TProgressbar", troughcolor=FIELD, background=ACCENT, bordercolor=FIELD,
                     lightcolor=ACCENT, darkcolor=ACCENT)
        self.root.option_add("*TCombobox*Listbox.background", FIELD)
        self.root.option_add("*TCombobox*Listbox.foreground", FG)
        self.root.option_add("*TCombobox*Listbox.selectBackground", ACCENT)

    def card(self, parent=None, pady=6):
        f = tk.Frame(parent or self.root, bg=CARD, padx=16, pady=12)
        f.pack(fill="x", padx=16, pady=pady)
        return f

    def button(self, parent, text, cmd, primary=False):
        return tk.Button(parent, text=text, command=cmd, bg=ACCENT if primary else FIELD, fg="white",
                         activebackground="#7aa2ff" if primary else "#3a4260", activeforeground="white",
                         relief="flat", bd=0, padx=14, pady=7, font=("Segoe UI Semibold", 9), cursor="hand2")

    def check(self, parent, text, key, extra=None):
        var = tk.BooleanVar(value=bool(CFG[key]))
        def cb():
            CFG[key] = var.get()
            T.dirty = True
            T.last = {}
            if extra:
                extra(var.get())
        tk.Checkbutton(parent, text=text, variable=var, command=cb, bg=CARD, fg=FG, activebackground=CARD,
                       activeforeground=FG, selectcolor=FIELD, font=("Segoe UI", 10), anchor="w", bd=0,
                       highlightthickness=0, cursor="hand2").pack(fill="x", pady=1)

    def build(self):
        r = self.root
        head = tk.Frame(r, bg=BG)
        head.pack(fill="x", padx=16, pady=(14, 4))
        tk.Label(head, text="Touchpad Distance", bg=BG, fg=FG, font=("Segoe UI Semibold", 13)).pack(side="left")
        self.pill = tk.Label(head, text="", font=("Segoe UI Semibold", 9), padx=10, pady=3, cursor="hand2")
        self.pill.pack(side="right")
        self.pill.bind("<Button-1>", lambda e: self.toggle())

        hero = self.card()
        tk.Label(hero, text="DISTANCE TOTALE", bg=CARD, fg=MUTED, font=("Segoe UI Semibold", 8)).pack(anchor="w")
        row = tk.Frame(hero, bg=CARD)
        row.pack(anchor="w", pady=(2, 0))
        self.big = tk.Label(row, text="0", bg=CARD, fg=FG, font=("Segoe UI Semibold", 38))
        self.big.pack(side="left")
        self.bigu = tk.Label(row, text="cm", bg=CARD, fg=ACCENT, font=("Segoe UI Semibold", 16))
        self.bigu.pack(side="left", padx=(8, 0), pady=(14, 0))

        rowf = tk.Frame(r, bg=BG)
        rowf.pack(fill="x", padx=16, pady=6)
        self.today = self.stat(rowf, "AUJOURD'HUI", 0)
        self.sess = self.stat(rowf, "SESSION", 1)
        rowf.columnconfigure(0, weight=1, uniform="a")
        rowf.columnconfigure(1, weight=1, uniform="a")

        opt = self.card()
        tk.Label(opt, text="CE QUI EST COMPTÉ", bg=CARD, fg=MUTED, font=("Segoe UI Semibold", 8)).pack(anchor="w", pady=(0, 4))
        self.check(opt, "Mouvements (1 doigt)", "count_move")
        self.check(opt, "Drag (clic maintenu + déplacement)", "count_drag")
        self.check(opt, "Scroll (2 doigts)", "count_scroll")

        ru = tk.Frame(opt, bg=CARD)
        ru.pack(fill="x", pady=(10, 0))
        tk.Label(ru, text="Unité", bg=CARD, fg=FG, font=("Segoe UI", 10)).pack(side="left")
        self.unit_var = tk.StringVar(value=CFG["unit"] if CFG["unit"] in ["Auto"] + list(UNITS) else "Auto")
        cbx = ttk.Combobox(ru, textvariable=self.unit_var, values=["Auto"] + list(UNITS), state="readonly", width=10)
        cbx.pack(side="right")
        cbx.bind("<<ComboboxSelected>>", self.on_unit)

        # SUPPRIMÉ : les 3 cases à cocher (startup, check_updates, auto_install)

        cal = self.card()
        tk.Label(cal, text="CALIBRAGE", bg=CARD, fg=MUTED, font=("Segoe UI Semibold", 8)).pack(anchor="w")
        self.cal_info = tk.Label(cal, text="", bg=CARD, fg=FG, font=("Segoe UI", 9), anchor="w", justify="left")
        self.cal_info.pack(fill="x", pady=(2, 8))
        rc = tk.Frame(cal, bg=CARD)
        rc.pack(anchor="w")
        self.button(rc, "Calibrer à la règle", self.calibrer).pack(side="left")
        self.button(rc, "Revenir à l'auto", self.auto_cal).pack(side="left", padx=(8, 0))

        bt = tk.Frame(r, bg=BG)
        bt.pack(fill="x", padx=16, pady=(6, 4))
        self.button(bt, "Pause / Reprendre", self.toggle, primary=True).pack(side="left")
        self.button(bt, "Remettre à zéro", self.reset).pack(side="left", padx=(8, 0))

        tk.Label(r, text="Alt + Ctrl droit = pause / reprise  ·  la croix réduit dans les icônes cachées",
                 bg=BG, fg=MUTED, font=("Segoe UI", 8)).pack(pady=(6, 2))

        ur = tk.Frame(r, bg=BG)
        ur.pack(fill="x", padx=16, pady=(0, 10))
        tk.Label(ur, text=f"v{VERSION}", bg=BG, fg=MUTED, font=("Segoe UI", 8)).pack(side="left")
        # SUPPRIMÉ : le bouton "Rechercher une mise à jour"

    def stat(self, parent, title, col):
        f = tk.Frame(parent, bg=CARD, padx=14, pady=10)
        f.grid(row=0, column=col, sticky="nsew", padx=(0, 6) if col == 0 else (6, 0))
        tk.Label(f, text=title, bg=CARD, fg=MUTED, font=("Segoe UI Semibold", 8)).pack(anchor="w")
        lbl = tk.Label(f, text="0 cm", bg=CARD, fg=FG, font=("Segoe UI Semibold", 15))
        lbl.pack(anchor="w")
        return lbl

    def on_unit(self, _e=None):
        CFG["unit"] = self.unit_var.get()
        T.dirty = True
        self.refresh()

    def toggle(self):
        T.paused = not T.paused
        T.last = {}
        self.flash(playing=not T.paused)
        self.refresh()

    def reset(self):
        if messagebox.askyesno("Remettre à zéro", "Remettre le total, aujourd'hui et la session à 0 ?",
                               parent=self.root):
            CFG["total_cm"] = 0.0
            CFG["today_cm"] = 0.0
            T.session = 0.0
            T.last = {}
            T.dirty = True
            self.refresh()

    def auto_cal(self):
        if not T.auto:
            messagebox.showinfo("Calibrage auto", "Ce pavé n'indique pas sa taille : utilise « Calibrer à la règle ».",
                                parent=self.root)
            return
        T.ux, T.uy = T.auto
        T.src = "auto"
        CFG["calib"] = None
        T.dirty = True
        self.refresh()

    def calibrer(self):
        if not T.seen:
            messagebox.showinfo("Calibrage", "Touche d'abord le pavé avec un doigt pour qu'il soit détecté.",
                                parent=self.root)
            return
        if self.wiz is not None and self.wiz.winfo_exists():
            self.wiz.lift()
            return
        sc = self.sc
        win = self.wiz = tk.Toplevel(self.root)
        win.title("Calibrage")
        win.configure(bg=BG)
        win.resizable(False, False)
        win.transient(self.root)
        tk.Label(win, bg=BG, fg=FG, font=("Segoe UI", 10), justify="left", wraplength=int(380 * sc),
                 text="1. Mesure à la règle la zone tactile de ton pavé (largeur × hauteur, en cm).\n\n"
                      "2. Fais glisser ton doigt sur tout le pavé : une grande diagonale d'un coin à l'autre "
                      "suffit. Les barres montrent la zone atteinte, vise ~100 %.\n\n"
                      "(Le but : que le script apprenne les valeurs min/max que le pavé renvoie à gauche, à droite, "
                      "en haut et en bas. Les coins ne sont pas obligatoires, c'est juste le plus rapide.)"
                 ).pack(padx=18, pady=(16, 10), anchor="w")
        form = tk.Frame(win, bg=BG)
        form.pack(padx=18, anchor="w")
        wv = tk.StringVar(value=f"{T.rx / T.ux:.1f}" if T.ux else "")
        hv = tk.StringVar(value=f"{T.ry / T.uy:.1f}" if T.uy else "")
        for i, (txt, var) in enumerate((("Largeur (cm)", wv), ("Hauteur (cm)", hv))):
            tk.Label(form, text=txt, bg=BG, fg=FG, font=("Segoe UI", 10), width=14, anchor="w").grid(row=i, column=0, pady=3)
            tk.Entry(form, textvariable=var, width=8, bg=FIELD, fg=FG, insertbackground=FG, relief="flat",
                     font=("Segoe UI", 10)).grid(row=i, column=1, pady=3, sticky="w")
        bars = tk.Frame(win, bg=BG)
        bars.pack(padx=18, pady=(12, 4), anchor="w")
        pbx = ttk.Progressbar(bars, length=int(240 * sc), maximum=100)
        pby = ttk.Progressbar(bars, length=int(240 * sc), maximum=100)
        lx = tk.Label(bars, bg=BG, fg=MUTED, font=("Segoe UI", 9), width=8)
        ly = tk.Label(bars, bg=BG, fg=MUTED, font=("Segoe UI", 9), width=8)
        tk.Label(bars, text="Largeur", bg=BG, fg=FG, font=("Segoe UI", 9), width=8, anchor="w").grid(row=0, column=0, pady=3)
        pbx.grid(row=0, column=1, padx=6)
        lx.grid(row=0, column=2)
        tk.Label(bars, text="Hauteur", bg=BG, fg=FG, font=("Segoe UI", 9), width=8, anchor="w").grid(row=1, column=0, pady=3)
        pby.grid(row=1, column=1, padx=6)
        ly.grid(row=1, column=2)
        def reset_ext():
            T.ext = [1e9, -1e9, 1e9, -1e9]
        def close():
            T.cal = False
            win.destroy()
        def upd():
            if not win.winfo_exists():
                return
            x0, x1, y0, y1 = T.ext
            px = max(0.0, (x1 - x0) / T.rx * 100) if T.rx and x1 > x0 else 0.0
            py = max(0.0, (y1 - y0) / T.ry * 100) if T.ry and y1 > y0 else 0.0
            pbx["value"], pby["value"] = px, py
            lx.config(text=f"{px:.0f} %")
            ly.config(text=f"{py:.0f} %")
            win.after(100, upd)
        def valider():
            try:
                W = float(wv.get().replace(",", "."))
                H = float(hv.get().replace(",", "."))
                assert W > 0 and H > 0
            except Exception:
                messagebox.showwarning("Calibrage", "Entre la largeur et la hauteur en cm (ex : 10.5).", parent=win)
                return
            x0, x1, y0, y1 = T.ext
            if T.rx and ((x1 - x0) < 0.6 * T.rx or (y1 - y0) < 0.6 * T.ry):
                messagebox.showwarning("Calibrage", "Zone atteinte trop petite : glisse ton doigt sur tout le pavé "
                                                    "(barres proches de 100 %).", parent=win)
                return
            T.ux, T.uy = (x1 - x0) / W, (y1 - y0) / H
            T.src = "manuel"
            CFG["calib"] = [T.ux, T.uy]
            T.dirty = True
            close()
            self.refresh()
            messagebox.showinfo("Calibrage", f"C'est calibré !\nTest : glisse 5 fois sur toute la largeur → "
                                             f"ça doit faire ≈ {5 * W:.0f} cm.", parent=self.root)
        bt = tk.Frame(win, bg=BG)
        bt.pack(padx=18, pady=(10, 16), anchor="w")
        self.button(bt, "Valider", valider, primary=True).pack(side="left")
        self.button(bt, "Recommencer", reset_ext).pack(side="left", padx=8)
        self.button(bt, "Annuler", close).pack(side="left")
        win.protocol("WM_DELETE_WINDOW", close)
        T.last = {}
        reset_ext()
        T.cal = True
        dark_titlebar(win)
        upd()

    # --- Mises à jour silencieuses ---
    def auto_check(self):
        check_updates()
        self.root.after(6 * 3600 * 1000, self.auto_check)

    def on_update_event(self, kind, payload):
        global RESTART, RESTART_HIDDEN
        if kind == "found":
            # Installation immédiate et silencieuse
            install_update(payload)
        elif kind == "installed":
            # Redémarrage silencieux (garde l'état caché/visible)
            RESTART = True
            RESTART_HIDDEN = self.root.state() == "withdrawn"
            self.quit()
            return True
        # Erreurs ignorées silencieusement
        return False

    def hide(self):
        self.root.withdraw()

    def show(self):
        r = self.root
        r.deiconify()
        r.lift()
        r.attributes("-topmost", True)
        r.after(300, lambda: r.attributes("-topmost", False))
        r.focus_force()
        self.refresh()

    def quit(self):
        T.cal = False
        save_cfg()
        TRAY.remove()
        self.root.destroy()

    def build_overlay(self):
        self.ov = tk.Toplevel(self.root)
        self.ov.withdraw()  # CORRECTIF : cache l'overlay dès sa création (plus de carré noir)
        self.ov.overrideredirect(True)
        self.ov.attributes("-topmost", True)
        sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        s = self.S
        self.ov.geometry(f"{s}x{s}+{(sw - s) // 2}+{(sh - s) // 2}")
        self.cv = tk.Canvas(self.ov, width=s, height=s, bg="#202020", highlightthickness=0)
        self.cv.pack()
        self.ov.withdraw()

    def _clickthrough(self):
        try:
            self.ov.update_idletasks()
            hwnd = user32.GetParent(self.ov.winfo_id()) or self.ov.winfo_id()
            st = user32.GetWindowLongW(hwnd, -20)
            user32.SetWindowLongW(hwnd, -20, st | 0x80000 | 0x20 | 0x80 | 0x08000000)
        except Exception:
            pass

    def flash(self, playing):
        if self._job:
            self.root.after_cancel(self._job)
        s = self.S
        self.cv.delete("all")
        if playing:
            self.cv.create_polygon(s * .34, s * .22, s * .34, s * .78, s * .78, s * .5, fill="white")
        else:
            self.cv.create_rectangle(s * .30, s * .22, s * .45, s * .78, fill="white", width=0)
            self.cv.create_rectangle(s * .55, s * .22, s * .70, s * .78, fill="white", width=0)
        self.ov.attributes("-alpha", 0.85)
        self.ov.deiconify()
        self.ov.lift()
        self._clickthrough()
        self._job = self.root.after(500, lambda: self._fade(time.perf_counter()))

    def _fade(self, t0):
        p = (time.perf_counter() - t0) / 0.3
        if p >= 1:
            self.ov.withdraw()
            self._job = None
            return
        self.ov.attributes("-alpha", 0.85 * (1 - p))
        self._job = self.root.after(15, self._fade, t0)

    def refresh(self):
        unit = CFG["unit"]
        v, u = convert(CFG["total_cm"], unit)
        self.big.config(text=fmt(v))
        self.bigu.config(text=u)
        v, u = convert(CFG["today_cm"], unit)
        self.today.config(text=f"{fmt(v)} {u}")
        v, u = convert(T.session, unit)
        self.sess.config(text=f"{fmt(v)} {u}")
        if T.paused:
            self.pill.config(text="❚❚  EN PAUSE", bg="#3a2e1c", fg=ORANGE)
        else:
            self.pill.config(text="●  EN COURS", bg="#173529", fg=GREEN)
        self.cal_info.config(text=T.info())

    def tick(self):
        now = time.time()
        down = (user32.GetAsyncKeyState(0xA3) & 0x8000) and (user32.GetAsyncKeyState(0x12) & 0x8000)
        if down and not self._was_down:
            self.toggle()
        self._was_down = bool(down)
        while True:
            try:
                c = CMDS.get_nowait()
            except queue.Empty:
                break
            if c == "show":
                self.show()
            elif c == "toggle":
                self.toggle()
            elif c == "quit":
                self.quit()
                return
        while True:
            try:
                ev = UPQ.get_nowait()
            except queue.Empty:
                break
            if self.on_update_event(*ev):
                return
        today = time.strftime("%Y-%m-%d")
        if CFG["day"] != today:
            CFG["day"] = today
            CFG["today_cm"] = 0.0
            T.dirty = True
        if now - self._ui > 0.1 and self.root.state() != "withdrawn":
            self.refresh()
            self._ui = now
        if now - self._save > 10:
            if T.dirty:
                save_cfg()
                T.dirty = False
            self._save = now
        if now - self._tip > 5:
            v, u = convert(CFG["total_cm"], CFG["unit"])
            TRAY.tip(f"Touchpad Distance : {fmt(v)} {u}" + (" (pause)" if T.paused else ""))
            self._tip = now
        self.root.after(30, self.tick)

def main():
    global MUTEX
    MUTEX = kernel32.CreateMutexW(None, False, "TouchpadDistanceTrackerMutex")
    if ctypes.get_last_error() == 183:
        user32.MessageBoxW(None, "Touchpad Distance tourne déjà : clique sur son icône dans les icônes cachées (^) de la barre des tâches.", "Touchpad Distance", 0x40)
        return
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass
    # Le programme se lance toujours au démarrage
    set_startup(True)
    app = App(hidden="--hidden" in sys.argv)
    T.dirty = True
    app.root.mainloop()
    save_cfg()
    if RESTART:
        kernel32.CloseHandle(MUTEX)
        subprocess.Popen([pyw_exe(), os.path.abspath(__file__)] + (["--hidden"] if RESTART_HIDDEN else []),
                        creationflags=0x08000000, close_fds=True)

if __name__ == "__main__":
    main()
