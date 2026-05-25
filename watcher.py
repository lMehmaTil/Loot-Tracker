"""
watcher.py - Datei-Watcher, SSE-Benachrichtigungen und Dungeon-Reload.
"""
import os, json, time, threading
from datetime import datetime
import state
import config
import log_parser


# ── SSE-Benachrichtigungen ─────────────────────────────────────────────────────

def _notify(msg):
    dead = []
    for q in state.sse_clients:
        try:
            q.append(msg)
        except Exception:
            dead.append(q)
    for q in dead:
        try:
            state.sse_clients.remove(q)
        except ValueError:
            pass


def notify_loot(entry):
    _notify(json.dumps({
        "type":      "loot",
        "timestamp": entry["timestamp"].isoformat(),
        "item":      entry["item"],
        "amount":    entry["amount"],
    }))


def notify_kopfgeld(entry):
    _notify(json.dumps({
        "type":      "kopfgeld",
        "timestamp": entry["timestamp"].isoformat(),
    }))


def notify_dungeon(entry):
    _notify(json.dumps({
        "type":         "dungeon",
        "timestamp":    entry["timestamp"].isoformat(),
        "dungeon_name": entry["dungeon_name"],
        "item":         entry["item"],
    }))


# ── Daten laden ────────────────────────────────────────────────────────────────

def load_log_file():
    if not os.path.exists(state.LOG_FILE):
        print("[WARNUNG] Log-Datei nicht gefunden: " + state.LOG_FILE)
        return
    entries, d_entries = [], []
    with open(state.LOG_FILE, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            e = log_parser.parse_line(line)
            if e:
                entries.append(e)
                d = log_parser.check_dungeon(e)
                if d:
                    d_entries.append(log_parser.make_dungeon_entry(e, d))
    with state.data_lock:
        state.loot_entries.clear()
        state.loot_entries.extend(entries)
        state.dungeon_entries.clear()
        state.dungeon_entries.extend(d_entries)
    print("[INFO] " + str(len(entries)) + " Loot-Eintraege, " + str(len(d_entries)) + " Dungeon-Runs geladen.")


def load_kopfgeld_file():
    if not os.path.exists(config.KOPFGELD_LOG):
        return
    entries = []
    with open(config.KOPFGELD_LOG, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            e = log_parser.parse_kopfgeld_line(line)
            if e:
                entries.append(e)
    with state.data_lock:
        state.kopfgeld_entries.clear()
        state.kopfgeld_entries.extend(entries)
    print("[INFO] " + str(len(entries)) + " Kopfgeld-Eintraege geladen.")


def reload_dungeon_entries():
    new_d = []
    with state.data_lock:
        for e in state.loot_entries:
            d = log_parser.check_dungeon(e)
            if d:
                new_d.append(log_parser.make_dungeon_entry(e, d))
        state.dungeon_entries.clear()
        state.dungeon_entries.extend(new_d)
    print("[INFO] " + str(len(new_d)) + " Dungeon-Runs nach Konfig-Update erkannt.")


# ── Datei-Watcher ──────────────────────────────────────────────────────────────

def tail_log_file():
    state.watcher_stop.clear()
    if not os.path.exists(state.LOG_FILE):
        print("[WARNUNG] Log-Datei nicht gefunden: " + state.LOG_FILE)
        return
    with open(state.LOG_FILE, "r", encoding="utf-8", errors="replace") as f:
        f.seek(0, 2)
        print("[INFO] Loot-Watcher gestartet: " + state.LOG_FILE)
        while not state.watcher_stop.is_set():
            line = f.readline()
            if line:
                entry = log_parser.parse_line(line)
                if entry:
                    with state.data_lock:
                        state.loot_entries.append(entry)
                    d = log_parser.check_dungeon(entry)
                    if d:
                        d_entry = log_parser.make_dungeon_entry(entry, d)
                        with state.data_lock:
                            state.dungeon_entries.append(d_entry)
                        notify_dungeon(d_entry)
                    notify_loot(entry)
            else:
                if os.path.exists(state.LOG_FILE) and f.tell() > os.path.getsize(state.LOG_FILE):
                    f.seek(0, 2)
                time.sleep(0.3)


def restart_watcher(new_log_file):
    state.LOG_FILE = new_log_file
    state.cfg["log_file"] = new_log_file
    config.save_config(state.cfg)
    state.watcher_stop.set()
    time.sleep(0.6)
    with state.data_lock:
        state.loot_entries.clear()
        state.dungeon_entries.clear()
    load_log_file()
    state.watcher_stop.clear()
    threading.Thread(target=tail_log_file, daemon=True).start()
    print("[INFO] Watcher neu gestartet mit: " + new_log_file)


def tail_kopfgeld_file():
    while not os.path.exists(config.KOPFGELD_LOG):
        time.sleep(3)
    with open(config.KOPFGELD_LOG, "r", encoding="utf-8", errors="replace") as f:
        f.seek(0, 2)
        while True:
            line = f.readline()
            if line:
                entry = log_parser.parse_kopfgeld_line(line)
                if entry:
                    with state.data_lock:
                        state.kopfgeld_entries.append(entry)
                    notify_kopfgeld(entry)
            else:
                if os.path.exists(config.KOPFGELD_LOG) and f.tell() > os.path.getsize(config.KOPFGELD_LOG):
                    f.seek(0, 2)
                time.sleep(1)


def run_kopfgeld_watcher():
    if not config.OCR_AVAILABLE:
        print("[INFO] Kopfgeld-Watcher deaktiviert (Tesseract nicht gefunden).")
        return

    pytesseract  = config.pytesseract
    mss_lib      = config.mss
    win32gui     = config.win32gui
    Image        = config.Image
    ImageFilter  = config.ImageFilter
    ImageEnhance = config.ImageEnhance

    print("[INFO] Kopfgeld-Watcher gestartet.")
    last_detected = None
    while True:
        try:
            results = []
            def cb(hwnd, _):
                title = win32gui.GetWindowText(hwnd)
                if (config.KOPFGELD_WINDOW_TITLE.lower() in title.lower()
                        and "loot tracker" not in title.lower()
                        and win32gui.IsWindowVisible(hwnd)):
                    r = win32gui.GetWindowRect(hwnd)
                    if (r[2]-r[0]) > 200 and (r[3]-r[1]) > 200:
                        results.append(r)
            win32gui.EnumWindows(cb, None)
            monitor_idx = int(state.cfg.get("monitor_index", 0))
            rect = results[0] if results else None
            active = monitor_idx > 0 or rect is not None
            if active:
                if last_detected and (datetime.now() - last_detected).total_seconds() < config.KOPFGELD_COOLDOWN:
                    time.sleep(config.KOPFGELD_SCAN_INTERVAL)
                    continue
                ct = state.cfg.get("chat_top",    config.CHAT_TOP_PCT_DEFAULT)
                cl = state.cfg.get("chat_left",   config.CHAT_LEFT_PCT_DEFAULT)
                cr = state.cfg.get("chat_right",  config.CHAT_RIGHT_PCT_DEFAULT)
                cb = state.cfg.get("chat_bottom", config.CHAT_BOTTOM_PCT_DEFAULT)
                with mss_lib.mss() as sct:
                    if monitor_idx > 0 and monitor_idx < len(sct.monitors):
                        m = sct.monitors[monitor_idx]
                        mw, mh = m["width"], m["height"]
                        region = {
                            "left":   m["left"] + int(mw * cl),
                            "top":    m["top"]  + int(mh * ct),
                            "width":  int(mw * (cr - cl)),
                            "height": int(mh * (cb - ct)),
                        }
                    elif rect:
                        x1, y1, x2, y2 = rect
                        ww, wh = x2-x1, y2-y1
                        region = {
                            "left":   x1 + int(ww * cl),
                            "top":    y1 + int(wh * ct),
                            "width":  int(ww * (cr - cl)),
                            "height": int(wh * (cb - ct)),
                        }
                    else:
                        time.sleep(config.KOPFGELD_SCAN_INTERVAL)
                        continue
                    shot = sct.grab(region)
                    img  = Image.frombytes("RGB", shot.size, shot.rgb)
                img  = img.resize((img.width*2, img.height*2), Image.LANCZOS)
                img  = ImageEnhance.Contrast(img.convert("L")).enhance(3.0)
                img  = img.filter(ImageFilter.SHARPEN)
                text = pytesseract.image_to_string(img, config="--psm 6 -l deu+eng").lower()
                if any("kopfgelder" in ln and "abgeschlossen" in ln for ln in text.splitlines()):
                    now  = datetime.now()
                    line = "[" + now.strftime("%d/%m/%y") + "] [" + now.strftime("%H:%M:%S") + "]: Kopfgelder abgeschlossen\n"
                    with open(config.KOPFGELD_LOG, "a", encoding="utf-8") as fh:
                        fh.write(line)
                    last_detected = now
                    print("[KOPFGELD] Erkannt: " + now.strftime("%H:%M:%S"))
        except Exception as e:
            print("[KOPFGELD-FEHLER] " + str(e))
        time.sleep(config.KOPFGELD_SCAN_INTERVAL)
