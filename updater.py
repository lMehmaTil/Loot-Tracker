"""
updater.py – Prüft GitHub auf neue Version und aktualisiert LootTracker.
Wird beim Start von main.py aufgerufen. Kehrt zurück wenn kein Update nötig.
"""

import os
import sys
import zipfile
import tempfile
import threading
import subprocess
import tkinter as tk
from tkinter import ttk

import requests

# ── Konfiguration ──────────────────────────────────────────────────────────────
GITHUB_API  = "https://api.github.com/repos/IMehmaTil/Loot-Tracker/releases/latest"
VERSION_FILE = "version.txt"

# Diese Einträge aus der ZIP werden aktualisiert, alles andere bleibt unberührt
UPDATE_WHITELIST = {"LootTracker.exe", "dashboard.html", "version.txt"}
UPDATE_DIR_PREFIX = "icons/"
# ──────────────────────────────────────────────────────────────────────────────


def _exe_dir() -> str:
    """Gibt das Verzeichnis der laufenden EXE zurück (oder des Scripts)."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def _get_local_version() -> str:
    path = os.path.join(_exe_dir(), VERSION_FILE)
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read().strip()
    except FileNotFoundError:
        return "v0.0"


def _get_latest_release():
    """Gibt (tag_name, download_url) zurück oder (None, None) bei Fehler."""
    try:
        r = requests.get(GITHUB_API, timeout=6)
        if r.status_code != 200:
            return None, None
        data = r.json()
        tag = data.get("tag_name")
        for asset in data.get("assets", []):
            name = asset.get("name", "")
            if name.endswith(".zip"):
                return tag, asset["browser_download_url"]
    except Exception:
        pass
    return None, None


def _should_extract(member: str) -> bool:
    """True wenn die Datei aus der ZIP übernommen werden soll."""
    # Führendes Verzeichnis abschneiden (z.B. "LootTracker-v1.1/LootTracker.exe")
    parts = member.replace("\\", "/").split("/", 1)
    name = parts[1] if len(parts) > 1 else parts[0]
    if not name:
        return False
    if name in UPDATE_WHITELIST:
        return True
    if name.startswith(UPDATE_DIR_PREFIX):
        return True
    return False


def _strip_root(member: str) -> str:
    """Entfernt ein optionales führendes Verzeichnis aus dem ZIP-Pfad."""
    parts = member.replace("\\", "/").split("/", 1)
    return parts[1] if len(parts) > 1 else parts[0]


# ── Tkinter-Fenster ───────────────────────────────────────────────────────────

class _UpdateWindow:
    BG      = "#1a1a2e"
    ACCENT  = "#e94560"
    FG      = "#ffffff"
    TROUGH  = "#0f3460"

    def __init__(self, latest_version: str):
        self.root = tk.Tk()
        self.root.title("Loot Tracker – Update")
        self.root.geometry("420x150")
        self.root.resizable(False, False)
        self.root.configure(bg=self.BG)
        self.root.protocol("WM_DELETE_WINDOW", lambda: None)  # Schließen sperren

        # Zentrieren
        self.root.update_idletasks()
        sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        self.root.geometry(f"420x150+{(sw-420)//2}+{(sh-150)//2}")

        tk.Label(
            self.root, text="Loot Tracker Update",
            bg=self.BG, fg=self.ACCENT,
            font=("Segoe UI", 13, "bold")
        ).pack(pady=(14, 2))

        self._status = tk.StringVar(value=f"Neue Version gefunden: {latest_version}")
        tk.Label(
            self.root, textvariable=self._status,
            bg=self.BG, fg=self.FG,
            font=("Segoe UI", 9)
        ).pack()

        style = ttk.Style()
        style.theme_use("default")
        style.configure(
            "red.Horizontal.TProgressbar",
            troughcolor=self.TROUGH,
            background=self.ACCENT,
            darkcolor=self.ACCENT,
            lightcolor=self.ACCENT,
            bordercolor=self.TROUGH,
        )
        self._bar = ttk.Progressbar(
            self.root, style="red.Horizontal.TProgressbar",
            orient="horizontal", length=370, mode="determinate"
        )
        self._bar.pack(pady=14)

    def set_status(self, text: str):
        self._status.set(text)
        self.root.update_idletasks()

    def set_progress(self, value: int):
        self._bar["value"] = value
        self.root.update_idletasks()

    def schedule(self, delay_ms: int, fn):
        self.root.after(delay_ms, fn)

    def mainloop(self):
        self.root.mainloop()

    def destroy(self):
        self.root.destroy()


# ── Update-Prozess ────────────────────────────────────────────────────────────

def _do_update(download_url: str, latest_version: str, win: _UpdateWindow):
    """Läuft in einem Background-Thread."""
    exe_dir = _exe_dir()

    try:
        # 1) Download
        win.schedule(0, lambda: win.set_status("Lade Update herunter..."))
        r = requests.get(download_url, stream=True, timeout=60)
        total = int(r.headers.get("content-length", 0))

        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".zip")
        downloaded = 0
        for chunk in r.iter_content(chunk_size=16384):
            if chunk:
                tmp.write(chunk)
                downloaded += len(chunk)
                if total:
                    pct = int(downloaded / total * 65)
                    win.schedule(0, lambda p=pct: win.set_progress(p))
        tmp.close()

        # 2) Entpacken
        win.schedule(0, lambda: win.set_status("Installiere Update..."))
        win.schedule(0, lambda: win.set_progress(70))

        with zipfile.ZipFile(tmp.name, "r") as zf:
            members = [m for m in zf.namelist() if _should_extract(m)]
            for i, member in enumerate(members):
                target_name = _strip_root(member)
                if not target_name:
                    continue
                target_path = os.path.join(exe_dir, target_name)
                if member.endswith("/"):
                    os.makedirs(target_path, exist_ok=True)
                else:
                    os.makedirs(os.path.dirname(target_path) or exe_dir, exist_ok=True)
                    with zf.open(member) as src, open(target_path, "wb") as dst:
                        dst.write(src.read())
                pct = 70 + int((i + 1) / max(len(members), 1) * 25)
                win.schedule(0, lambda p=pct: win.set_progress(p))

        os.unlink(tmp.name)

        # 3) Fertig → Neustart
        win.schedule(0, lambda: win.set_status("Update abgeschlossen! Starte neu..."))
        win.schedule(0, lambda: win.set_progress(100))
        win.schedule(1800, lambda: _restart(win, exe_dir))

    except Exception as e:
        win.schedule(0, lambda: win.set_status(f"Fehler beim Update: {e}"))
        win.schedule(4000, win.destroy)


def _restart(win: _UpdateWindow, exe_dir: str):
    win.destroy()
    exe = os.path.join(exe_dir, "LootTracker.exe")
    subprocess.Popen([exe])
    sys.exit(0)


# ── Öffentliche API ───────────────────────────────────────────────────────────

def check_and_update():
    """
    Prüft auf eine neue Version und zeigt ggf. das Update-Fenster.
    Kehrt sofort zurück wenn kein Update verfügbar ist.
    Nach einem erfolgreichen Update wird die EXE neu gestartet (sys.exit).
    """
    local   = _get_local_version()
    latest, url = _get_latest_release()

    if not latest or not url or latest == local:
        return  # Kein Update nötig – normal weiterstarten

    win = _UpdateWindow(latest)
    t = threading.Thread(target=_do_update, args=(url, latest, win), daemon=True)
    t.start()
    win.mainloop()  # Blockiert bis Fenster geschlossen wird (nach Neustart)
