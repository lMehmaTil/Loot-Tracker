"""
state.py – Gemeinsamer, veränderbarer Laufzeit-Zustand.
Alle anderen Module importieren dieses Modul und greifen über
Attribut-Zugriff zu (state.LOG_FILE, state.cfg, ...).
"""
import threading
import config

# Laufzeit-Konfiguration (veränderlich – wird von watcher.py aktualisiert)
cfg      = config.load_config()
LOG_FILE = cfg.get("log_file", config.DEFAULT_LOG)

# Eintrags-Listen (thread-sicher über data_lock)
loot_entries     = []
kopfgeld_entries = []
dungeon_entries  = []

# SSE-Clients (Liste von Listen, jeder Client hat eine eigene Queue)
sse_clients = []

# Thread-Lock für alle Listen
data_lock = threading.Lock()

# Event zum Stoppen des Log-Watchers
watcher_stop = threading.Event()

# pywebview-Fenster (wird in main.py gesetzt)
webview_window = None
