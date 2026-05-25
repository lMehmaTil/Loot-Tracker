"""
dps_zone.py – Automatische Farm-Zonen-Erkennung via DPS-Meter-Dateien.

Liest den dpsmeter/-Ordner des Spiels. Jede JSON-Datei ist eine Kampfsession
mit Mob-IDs. Gleiche Mob-ID-Kombination = gleiche Farm-Zone.
Der Nutzer benennt jede Signatur einmal; danach erkennt der Tracker
die Zone automatisch.
"""
import os, json, glob, time, threading
from datetime import datetime

import state
import config


# ── Hilfsfunktionen ───────────────────────────────────────────────────────────

def _mob_signature(session_data: dict) -> str:
    """
    Erstellt einen sortierten String aus allen Mob-IDs einer Session.
    '1_0' wird ignoriert (kommt immer vor, enthält keine Ortsinformation).
    """
    ids = set()
    for entry in session_data.get("damage", []):
        for mob_id in entry.get("damage_data", {}).keys():
            if mob_id != "1_0":
                ids.add(mob_id)
    return "|".join(sorted(ids))


def _load_json(filepath: str) -> dict | None:
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _dps_dir() -> str:
    """Leitet den dpsmeter-Pfad aus dem konfigurierten Log-Pfad ab."""
    game_dir = os.path.dirname(state.LOG_FILE)
    return os.path.join(game_dir, "dpsmeter")


# ── Sessions laden ────────────────────────────────────────────────────────────

def load_dps_sessions() -> list:
    """Lädt alle bestehenden DPS-Sessions aus dem dpsmeter-Ordner."""
    dps_dir = _dps_dir()
    if not os.path.exists(dps_dir):
        print(f"[DPS Zone] Ordner nicht gefunden: {dps_dir}")
        return []

    sessions = []
    for filepath in glob.glob(os.path.join(dps_dir, "*.json")):
        data = _load_json(filepath)
        if not data:
            continue
        sig = _mob_signature(data)
        sessions.append({
            "file":      filepath,
            "start":     data.get("start", 0),
            "end":       data.get("end",   0),
            "signature": sig,
        })

    sessions.sort(key=lambda x: x["start"])
    print(f"[DPS Zone] {len(sessions)} Sessions geladen.")
    return sessions


# ── Zone-Lookup ───────────────────────────────────────────────────────────────

def get_zone_for_timestamp(ts_dt: datetime) -> str | None:
    """
    Gibt den Zone-Namen für einen Loot-Timestamp zurück.

    Strategie: "Sticky Zone" – die zuletzt aktive Zone bleibt bis zu
    60 Minuten gültig. Wechselt erst wenn eine DPS-Session mit einer
    anderen bekannten Signatur auftaucht.
    """
    ts = ts_dt.timestamp()
    zone_mappings: dict = state.cfg.get("zone_mappings", {})

    with state.data_lock:
        sessions = sorted(state.dps_sessions, key=lambda x: x["start"])

    # Finde die letzte DPS-Session, die VOR dem Loot-Timestamp (+ 2 Min Puffer) liegt
    # und eine bekannte Signatur hat.
    last_known: dict | None = None

    for s in sessions:
        if s["start"] > ts + 120:   # 2 Min in die Zukunft schauen (kurze Lags)
            break
        sig = s.get("signature", "")
        if sig and sig in zone_mappings:
            last_known = s

    if not last_known:
        return None

    # Zone ist gültig wenn der Loot innerhalb von 60 Min nach Session-Ende liegt
    if (ts - last_known["end"]) <= 3600:
        return zone_mappings[last_known["signature"]]

    return None


# ── Neue Session verarbeiten ──────────────────────────────────────────────────

def _process_new_session(filepath: str):
    """Liest eine neue DPS-JSON-Datei und aktualisiert den State."""
    time.sleep(0.5)   # kurz warten bis Datei vollständig geschrieben
    data = _load_json(filepath)
    if not data:
        return

    sig = _mob_signature(data)
    session = {
        "file":      filepath,
        "start":     data.get("start", 0),
        "end":       data.get("end",   0),
        "signature": sig,
    }

    zone_mappings: dict = state.cfg.get("zone_mappings", {})
    zone_name = zone_mappings.get(sig)

    with state.data_lock:
        state.dps_sessions.append(session)
        if zone_name:
            state.current_zone = zone_name
            print(f"[DPS Zone] Zone erkannt: {zone_name}")
        elif sig:
            # Unbekannte Signatur – im State merken damit UI sie anzeigen kann
            state.unknown_dps_signature = sig
            print(f"[DPS Zone] Unbekannte Signatur: {sig}")

    # SSE-Benachrichtigung
    try:
        import watcher as w
        import json as _j
        w._notify(_j.dumps({
            "type": "zone",
            "zone": zone_name or "",
            "signature": sig,
        }))
    except Exception:
        pass


# ── Watcher-Thread ─────────────────────────────────────────────────────────────

def _watch_loop():
    dps_dir = _dps_dir()
    if not os.path.exists(dps_dir):
        # Warte bis der Ordner existiert (Spiel noch nicht gestartet)
        while not os.path.exists(dps_dir):
            time.sleep(5)

    known = set(os.listdir(dps_dir))
    print(f"[DPS Zone] Watcher aktiv: {dps_dir}")

    while True:
        time.sleep(2)
        try:
            current = set(os.listdir(dps_dir))
            for fname in current - known:
                if fname.endswith(".json"):
                    _process_new_session(os.path.join(dps_dir, fname))
            known = current
        except Exception as e:
            print(f"[DPS Zone] Watcher-Fehler: {e}")


def start_dps_watcher():
    """Initialisiert und startet den DPS-Zone-Watcher."""
    sessions = load_dps_sessions()
    zone_mappings: dict = state.cfg.get("zone_mappings", {})

    with state.data_lock:
        state.dps_sessions = sessions
        # Beim Start: prüfen ob es unbenannte Signaturen gibt
        for s in sessions:
            sig = s.get("signature", "")
            if not sig:
                continue
            if sig in zone_mappings:
                # Letzte bekannte Zone als aktuelle setzen
                state.current_zone = zone_mappings[sig]
            else:
                # Mindestens eine unbekannte Signatur → Badge zeigen
                if not state.unknown_dps_signature:
                    state.unknown_dps_signature = sig

    threading.Thread(target=_watch_loop, daemon=True).start()



# ── Statistik-Hilfsfunktion ───────────────────────────────────────────────────

def get_all_signatures() -> list:
    """
    Gibt alle bekannten Signaturen zurueck, angereichert mit dem
    konfigurierten Zone-Namen und Mob-Listen.
    """
    with state.data_lock:
        sessions = list(state.dps_sessions)

    zone_mappings: dict = state.cfg.get("zone_mappings", {})

    seen: dict = {}
    for s in sessions:
        sig = s.get("signature", "")
        if not sig:
            continue
        if sig not in seen:
            seen[sig] = {
                "signature":     sig,
                "mob_ids":       sig.split("|") if sig else [],
                "zone_name":     zone_mappings.get(sig, ""),
                "session_count": 0,
                "last_seen":     0,
            }
        seen[sig]["session_count"] += 1
        seen[sig]["last_seen"] = max(seen[sig]["last_seen"], s.get("end", 0))

    result = list(seen.values())
    result.sort(key=lambda x: x["last_seen"], reverse=True)
    return result
