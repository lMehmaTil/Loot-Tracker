"""
log_parser.py – Regex-Muster, Parse-Funktionen und Dungeon-Erkennung.
Liest aus state.cfg (Dungeon-Konfiguration), schreibt nichts zurück.
"""
import re
from datetime import datetime
import state

LINE_PATTERN     = re.compile(r"\[(\d{2}/\d{2}/\d{2})\] \[(\d{2}:\d{2}:\d{2})\]: You receive (\d+) (.+)\.")
KOPFGELD_PATTERN = re.compile(r"\[(\d{2}/\d{2}/\d{2})\] \[(\d{2}:\d{2}:\d{2})\]: Kopfgelder abgeschlossen")


def _parse_dt(date_str, time_str):
    try:
        return datetime.strptime(date_str + " " + time_str, "%d/%m/%y %H:%M:%S")
    except ValueError:
        return None


def parse_line(line):
    """Parst eine Loot-Zeile. Gibt dict oder None zurück."""
    m = LINE_PATTERN.match(line.strip())
    if not m:
        return None
    d, t, amount, item = m.groups()
    dt = _parse_dt(d, t)
    return {"timestamp": dt, "item": item.strip(), "amount": int(amount)} if dt else None


def parse_kopfgeld_line(line):
    """Parst eine Kopfgeld-Zeile. Gibt dict oder None zurück."""
    m = KOPFGELD_PATTERN.match(line.strip())
    if not m:
        return None
    dt = _parse_dt(m.group(1), m.group(2))
    return {"timestamp": dt} if dt else None


def check_dungeon(entry):
    """Gibt Dungeon-Konfig zurück, wenn das Item einem konfigurierten Kisten-Item entspricht."""
    dungeon_cfg = state.cfg.get("dungeons", [])
    item_lower  = entry["item"].strip().lower()
    for d in dungeon_cfg:
        if d.get("chest_item", "").strip().lower() == item_lower:
            return d
    return None


def make_dungeon_entry(loot_entry, d_cfg):
    """Erstellt einen Dungeon-Eintrag aus einem Loot-Eintrag und der Dungeon-Konfig."""
    return {
        "timestamp":    loot_entry["timestamp"],
        "item":         loot_entry["item"],
        "dungeon_name": d_cfg.get("name", loot_entry["item"]),
        "cost":         int(d_cfg.get("cost", 0)),
    }
