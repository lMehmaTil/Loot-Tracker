"""
config.py - Konstanten, Pfade, Config-I/O und OCR-Verfügbarkeit.
"""
import os, sys, json

# ── Pfade ──────────────────────────────────────────────────────────────────────
if getattr(sys, "frozen", False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = BASE_DIR

HOST             = "127.0.0.1"
PORT             = 5000
CONFIG_FILE      = os.path.join(DATA_DIR, "config.json")
KOPFGELD_LOG     = os.path.join(DATA_DIR, "kopfgelder.log")
DEFAULT_LOG      = r"C:\Users\Mehmet\Desktop\Nihor2 - Chronicles of Jinteia (1)\Nihor2 - Chronicles of Jinteia\info_chat_loot.log"
ICONS_DIR        = os.path.join(DATA_DIR, "icons")
ICON_MAP_FILE    = os.path.join(DATA_DIR, "icon_map.json")

# ── Schwellwerte / Tuning ──────────────────────────────────────────────────────
PAUSE_THRESHOLD_MIN    = 3
KOPFGELD_WINDOW_TITLE  = "Nihor2"
KOPFGELD_SCAN_INTERVAL = 0.5
KOPFGELD_COOLDOWN      = 45

# Standard-Chat-Region (prozentual zum Spielfenster)
CHAT_TOP_PCT_DEFAULT    = 0.62
CHAT_LEFT_PCT_DEFAULT   = 0.25
CHAT_RIGHT_PCT_DEFAULT  = 0.75
CHAT_BOTTOM_PCT_DEFAULT = 1.0

# ── OCR (optional) ────────────────────────────────────────────────────────────
try:
    import pytesseract, mss, win32gui
    from PIL import Image, ImageFilter, ImageEnhance
    # Tesseract an mehreren möglichen Orten suchen
    _TESSERACT_PATHS = [
        r"C:\Program Files\Tesseract-OCR\tesseract.exe",
        r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
        r"C:\Users\Public\Tesseract-OCR\tesseract.exe",
    ]
    # Auch über PATH versuchen
    import shutil as _shutil
    _from_path = _shutil.which("tesseract")
    if _from_path:
        _TESSERACT_PATHS.insert(0, _from_path)

    _found = next((p for p in _TESSERACT_PATHS if os.path.exists(p)), None)
    # Auch aus config.json gespeicherten Pfad prüfen
    try:
        import json as _json
        _cfg_path = os.path.join(DATA_DIR, "config.json")
        if os.path.exists(_cfg_path):
            _saved = _json.load(open(_cfg_path, encoding="utf-8")).get("tesseract_path", "")
            if _saved and os.path.exists(_saved):
                _found = _saved
    except Exception:
        pass
    if _found:
        pytesseract.pytesseract.tesseract_cmd = _found
        OCR_AVAILABLE = True
    else:
        OCR_AVAILABLE = False
except ImportError:
    pytesseract = mss = win32gui = Image = ImageFilter = ImageEnhance = None
    OCR_AVAILABLE = False


# ── Config I/O ────────────────────────────────────────────────────────────────
def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {
        "log_file":    DEFAULT_LOG,
        "kopfgeld_cost": 0,
        "dungeons":    [],
        "chat_top":    CHAT_TOP_PCT_DEFAULT,
        "chat_left":   CHAT_LEFT_PCT_DEFAULT,
        "chat_right":  CHAT_RIGHT_PCT_DEFAULT,
        "chat_bottom": CHAT_BOTTOM_PCT_DEFAULT,
    }


def save_config(data):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def load_icon_map():
    if os.path.exists(ICON_MAP_FILE):
        try:
            with open(ICON_MAP_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}
