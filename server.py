"""
server.py – Flask-App, alle API-Routen und pywebview-Api-Klasse.
Abhängigkeiten: state, config, stats, watcher, log_parser.
"""
import os, json, time, threading
from flask import Flask, Response, jsonify, send_from_directory, request
import webview
import requests as http_requests

import state
import config
import stats as stats_module
import watcher
import log_parser


app = Flask(__name__, static_folder="static")


# ── Statische Assets ──────────────────────────────────────────────────────────

@app.route("/")
def index():
    return send_from_directory(config.BASE_DIR, "dashboard.html")


@app.route("/icons/<path:filename>")
def serve_icon(filename):
    if not os.path.exists(config.ICONS_DIR):
        return "", 404
    return send_from_directory(config.ICONS_DIR, filename)


# ── Icon-API ──────────────────────────────────────────────────────────────────

@app.route("/api/icons")
def api_icons():
    icon_map = config.load_icon_map()
    if not os.path.exists(config.ICONS_DIR):
        return jsonify({"icons": [], "map": icon_map})
    exts  = {".png", ".jpg", ".jpeg", ".gif", ".webp"}
    files = [f for f in os.listdir(config.ICONS_DIR)
             if os.path.splitext(f)[1].lower() in exts]
    return jsonify({"icons": files, "map": icon_map})


@app.route("/api/icons/map", methods=["POST"])
def api_icons_map_save():
    data = request.get_json()
    os.makedirs(config.ICONS_DIR, exist_ok=True)
    with open(config.ICON_MAP_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    return jsonify({"ok": True})


# ── Version & Update-API ──────────────────────────────────────────────────────

GITHUB_VERSION_URL = "https://raw.githubusercontent.com/IMehmaTil/Loot-Tracker/main/latest_version.txt"

@app.route("/api/version")
def api_version():
    version_path = os.path.join(config.BASE_DIR, "version.txt")
    try:
        with open(version_path, "r", encoding="utf-8") as f:
            version = f.read().strip()
    except FileNotFoundError:
        version = "v0.0"
    return jsonify({"version": version})


@app.route("/api/check_update")
def api_check_update():
    try:
        r = http_requests.get(GITHUB_VERSION_URL, timeout=8)
        if r.status_code != 200:
            return jsonify({"error": "Datei nicht gefunden (Status " + str(r.status_code) + ")"}), 200
        latest = r.text.strip()
        return jsonify({"tag_name": latest})
    except Exception as e:
        return jsonify({"error": str(e)}), 200


# ── Statistik-API ─────────────────────────────────────────────────────────────

@app.route("/api/stats/<period>")
def api_stats(period):
    if period not in ("hour", "today", "week", "all"):
        return jsonify({"error": "Ungültiger Zeitraum"}), 400
    return jsonify(stats_module.compute_stats(period))


@app.route("/api/kopfgelder/<period>")
def api_kopfgelder(period):
    if period not in ("hour", "today", "week", "all"):
        return jsonify({"error": "Ungültiger Zeitraum"}), 400
    return jsonify(stats_module.compute_kopfgeld_stats(period))


@app.route("/api/dungeons/<period>")
def api_dungeons(period):
    if period not in ("hour", "today", "week", "all"):
        return jsonify({"error": "Ungültiger Zeitraum"}), 400
    return jsonify(stats_module.compute_dungeon_stats(period))


# ── Konfig-API ────────────────────────────────────────────────────────────────

@app.route("/api/config", methods=["GET"])
def api_config_get():
    return jsonify({
        "log_file":      state.LOG_FILE,
        "log_exists":    os.path.exists(state.LOG_FILE),
        "is_configured": os.path.exists(config.CONFIG_FILE),
        "kopfgeld_cost": state.cfg.get("kopfgeld_cost", 0),
        "dungeons":      state.cfg.get("dungeons", []),
        "chat_top":      state.cfg.get("chat_top",    config.CHAT_TOP_PCT_DEFAULT),
        "chat_left":     state.cfg.get("chat_left",   config.CHAT_LEFT_PCT_DEFAULT),
        "chat_right":    state.cfg.get("chat_right",  config.CHAT_RIGHT_PCT_DEFAULT),
        "chat_bottom":   state.cfg.get("chat_bottom", config.CHAT_BOTTOM_PCT_DEFAULT),
        "ocr_available":      config.OCR_AVAILABLE,
        "monitor_index":      state.cfg.get("monitor_index", 0),
        "tesseract_path":     state.cfg.get("tesseract_path", ""),
        "pause_threshold_min": state.cfg.get("pause_threshold_min", config.PAUSE_THRESHOLD_MIN),
    })


@app.route("/api/config", methods=["POST"])
def api_config_post():
    data     = request.get_json()
    new_path = data.get("log_file", "").strip()
    changed  = False

    if "kopfgeld_cost" in data:
        state.cfg["kopfgeld_cost"] = max(0, int(data["kopfgeld_cost"] or 0))
        changed = True

    if "pause_threshold_min" in data:
        val = max(1, min(60, int(data["pause_threshold_min"] or 3)))
        state.cfg["pause_threshold_min"] = val
        config.PAUSE_THRESHOLD_MIN = val
        changed = True

    if "dungeons" in data:
        state.cfg["dungeons"] = data["dungeons"]
        changed = True
        threading.Thread(target=watcher.reload_dungeon_entries, daemon=True).start()

    if "monitor_index" in data:
        state.cfg["monitor_index"] = int(data["monitor_index"])
        changed = True

    if "tesseract_path" in data:
        tp = data["tesseract_path"].strip()
        state.cfg["tesseract_path"] = tp
        # Sofort anwenden wenn gültig
        import os as _os
        if tp and _os.path.exists(tp) and config.pytesseract:
            config.pytesseract.pytesseract.tesseract_cmd = tp
            config.OCR_AVAILABLE = True
        changed = True

    for key in ("chat_top", "chat_left", "chat_right", "chat_bottom"):
        if key in data:
            val = float(data[key])
            state.cfg[key] = max(0.0, min(1.0, val))
            changed = True

    if new_path and new_path != state.LOG_FILE:
        threading.Thread(target=watcher.restart_watcher, args=(new_path,), daemon=True).start()
        return jsonify({"ok": True, "log_file": new_path})

    if changed:
        config.save_config(state.cfg)

    return jsonify({"ok": True})


ITEM_CONFIG_FILE = os.path.join(config.BASE_DIR, "item_config.json")

@app.route("/api/item_config", methods=["GET"])
def api_item_config_get():
    try:
        if os.path.exists(ITEM_CONFIG_FILE):
            with open(ITEM_CONFIG_FILE, "r", encoding="utf-8") as f:
                return jsonify(json.load(f))
    except Exception:
        pass
    return jsonify({})

@app.route("/api/item_config", methods=["POST"])
def api_item_config_post():
    data = request.get_json()
    if not isinstance(data, dict):
        return jsonify({"ok": False, "error": "invalid"}), 400
    try:
        with open(ITEM_CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/validate_log", methods=["POST"])
def api_validate_log():
    data = request.get_json()
    path = data.get("path", "").strip()
    if not path:
        return jsonify({"valid": False, "reason": "empty"})
    if not os.path.exists(path):
        return jsonify({"valid": False, "reason": "not_found"})
    matches = 0
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            for i, line in enumerate(f):
                if i >= 200:
                    break
                if log_parser.LINE_PATTERN.match(line.strip()):
                    matches += 1
    except Exception as e:
        return jsonify({"valid": False, "reason": "read_error", "detail": str(e)})
    if matches > 0:
        return jsonify({"valid": True, "matches": matches})
    return jsonify({"valid": False, "reason": "no_matches"})


# ── Status-API ────────────────────────────────────────────────────────────────

@app.route("/api/status")
def api_status():
    from datetime import datetime
    with state.data_lock:
        lc = len(state.loot_entries)
        kc = len(state.kopfgeld_entries)
        dc = len(state.dungeon_entries)
    return jsonify({
        "log_file":         state.LOG_FILE,
        "log_exists":       os.path.exists(state.LOG_FILE),
        "total_entries":    lc,
        "kopfgeld_entries": kc,
        "dungeon_entries":  dc,
        "kopfgeld_watcher": config.OCR_AVAILABLE,
        "server_time":      datetime.now().isoformat(),
    })


# ── SSE-Stream ────────────────────────────────────────────────────────────────

@app.route("/stream")
def stream():
    q = []
    state.sse_clients.append(q)

    def gen():
        try:
            while True:
                if q:
                    yield "data: " + q.pop(0) + "\n\n"
                else:
                    yield ": heartbeat\n\n"
                    time.sleep(1)
        except GeneratorExit:
            pass
        finally:
            try:
                state.sse_clients.remove(q)
            except ValueError:
                pass

    return Response(gen(), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


# ── Kopfgeld löschen ─────────────────────────────────────────────────────────

@app.route("/api/kopfgelder/last", methods=["DELETE"])
def api_kopfgelder_delete_last():
    with state.data_lock:
        if not state.kopfgeld_entries:
            return jsonify({"ok": False, "reason": "empty"}), 404
        state.kopfgeld_entries.pop()
    try:
        if os.path.exists(config.KOPFGELD_LOG):
            with open(config.KOPFGELD_LOG, "r", encoding="utf-8") as f:
                lines = f.readlines()
            if lines:
                with open(config.KOPFGELD_LOG, "w", encoding="utf-8") as f:
                    f.writelines(lines[:-1])
    except Exception as e:
        print("[FEHLER] Log-Rewrite fehlgeschlagen: " + str(e))
    return jsonify({"ok": True})


# ── Monitor-Liste ─────────────────────────────────────────────────────────────

@app.route("/api/monitors")
def api_monitors():
    if not config.OCR_AVAILABLE:
        return jsonify({"monitors": []})
    try:
        with config.mss.mss() as sct:
            monitors = []
            for i, m in enumerate(sct.monitors[1:], 1):  # 0 = alle zusammen
                monitors.append({
                    "index": i,
                    "left":  m["left"],
                    "top":   m["top"],
                    "width": m["width"],
                    "height":m["height"],
                    "label": f"Monitor {i}: {m['width']}x{m['height']} @ ({m['left']},{m['top']})",
                })
        return jsonify({"monitors": monitors})
    except Exception as e:
        return jsonify({"monitors": [], "error": str(e)})


# ── Tesseract-Check ───────────────────────────────────────────────────────────

@app.route("/api/tesseract_check", methods=["POST"])
def api_tesseract_check():
    import os, subprocess
    data = request.get_json() or {}
    p    = data.get("path", "").strip()
    if not p:
        return jsonify({"ok": False, "reason": "empty"})
    if not os.path.exists(p):
        return jsonify({"ok": False, "reason": "not_found"})
    try:
        r = subprocess.run([p, "--version"], capture_output=True, text=True, timeout=5)
        ver = (r.stdout + r.stderr).strip().split("\n")[0]
        return jsonify({"ok": True, "path": p, "version": ver})
    except Exception as e:
        return jsonify({"ok": False, "reason": str(e)})


# ── OCR-Debug ─────────────────────────────────────────────────────────────────

@app.route("/api/ocr_debug")
def api_ocr_debug():
    import shutil, sys
    info = {"ocr_available": config.OCR_AVAILABLE, "checks": []}

    # Tesseract-Pfade prüfen
    paths = [
        r"C:\Program Files\Tesseract-OCR\tesseract.exe",
        r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
        r"C:\Users\Public\Tesseract-OCR\tesseract.exe",
    ]
    from_path = shutil.which("tesseract")
    if from_path:
        paths.insert(0, from_path)
    for p in paths:
        import os
        info["checks"].append({"path": p, "exists": os.path.exists(p)})

    # Pakete prüfen
    for pkg in ["pytesseract", "mss", "win32gui", "PIL"]:
        try:
            __import__(pkg)
            info["checks"].append({"package": pkg, "status": "ok"})
        except ImportError as e:
            info["checks"].append({"package": pkg, "status": "FEHLT: " + str(e)})

    info["frozen"] = getattr(sys, "frozen", False)
    return jsonify(info)


# ── OCR-Test ──────────────────────────────────────────────────────────────────

@app.route("/api/ocr_test", methods=["POST"])
def api_ocr_test():
    if not config.OCR_AVAILABLE:
        return jsonify({"error": "OCR nicht verfügbar (Tesseract nicht installiert)"})
    data = request.get_json() or {}
    ct = float(data.get("chat_top",    config.CHAT_TOP_PCT_DEFAULT))
    cl = float(data.get("chat_left",   config.CHAT_LEFT_PCT_DEFAULT))
    cr = float(data.get("chat_right",  config.CHAT_RIGHT_PCT_DEFAULT))
    cb = float(data.get("chat_bottom", config.CHAT_BOTTOM_PCT_DEFAULT))
    try:
        win32gui    = config.win32gui
        mss_lib     = config.mss
        Image       = config.Image
        ImageFilter = config.ImageFilter
        ImageEnhance= config.ImageEnhance
        pytesseract = config.pytesseract
        results = []
        def cb_fn(hwnd, _):
            title = win32gui.GetWindowText(hwnd)
            if (config.KOPFGELD_WINDOW_TITLE.lower() in title.lower()
                    and "loot tracker" not in title.lower()
                    and win32gui.IsWindowVisible(hwnd)):
                r = win32gui.GetWindowRect(hwnd)
                if (r[2]-r[0]) > 200 and (r[3]-r[1]) > 200:
                    results.append(r)
        win32gui.EnumWindows(cb_fn, None)
        if not results:
            return jsonify({"error": "Spielfenster nicht gefunden – ist Nihor2 geöffnet und sichtbar?"})
        monitor_idx = int(data.get("monitor_index", state.cfg.get("monitor_index", 0)))
        if monitor_idx > 0:
            # Direkt einen Monitor scannen (ohne Fenstersuche)
            with mss_lib.mss() as sct:
                if monitor_idx < len(sct.monitors):
                    m = sct.monitors[monitor_idx]
                    mw, mh = m["width"], m["height"]
                    region = {
                        "left":   m["left"] + int(mw * cl),
                        "top":    m["top"]  + int(mh * ct),
                        "width":  int(mw * (cr - cl)),
                        "height": int(mh * (cb - ct)),
                    }
                    shot = sct.grab(region)
                    img  = Image.frombytes("RGB", shot.size, shot.rgb)
                else:
                    return jsonify({"error": f"Monitor {monitor_idx} nicht gefunden"})
        else:
            x1, y1, x2, y2 = results[0]
            ww, wh = x2-x1, y2-y1
            region = {
                "left":   x1 + int(ww * cl),
                "top":    y1 + int(wh * ct),
                "width":  int(ww * (cr - cl)),
                "height": int(wh * (cb - ct)),
            }
            with mss_lib.mss() as sct:
                shot = sct.grab(region)
                img  = Image.frombytes("RGB", shot.size, shot.rgb)
        img  = img.resize((img.width*2, img.height*2), Image.LANCZOS)
        img  = ImageEnhance.Contrast(img.convert("L")).enhance(3.0)
        img  = img.filter(ImageFilter.SHARPEN)
        text = pytesseract.image_to_string(img, config="--psm 6 -l deu+eng").strip()
        # Vorschaubild als base64 zurückgeben
        import io, base64
        preview = img.resize((min(img.width, 600), min(img.height, 200)), Image.LANCZOS)
        buf = io.BytesIO()
        preview.save(buf, format="PNG")
        b64 = base64.b64encode(buf.getvalue()).decode()
        return jsonify({"text": text or "", "region": region, "preview": b64})
    except Exception as e:
        return jsonify({"error": str(e)})


# ── Flask starten ─────────────────────────────────────────────────────────────

def run_flask():
    app.run(
        host    = config.HOST,
        port    = config.PORT,
        debug   = False,
        use_reloader = False,
        threaded= True,
    )


# ── pywebview JS-API ──────────────────────────────────────────────────────────

class Api:
    def close_window(self):
        if state.webview_window:
            state.webview_window.destroy()

    def minimize_window(self):
        if state.webview_window:
            state.webview_window.minimize()

    def save_window_state(self, x, y, width, height):
        state.cfg.setdefault("window", {})
        state.cfg["window"]["x"]      = x
        state.cfg["window"]["y"]      = y
        state.cfg["window"]["width"]  = width
        state.cfg["window"]["height"] = height
        config.save_config(state.cfg)
