"""
stats.py – Statistik-Berechnungen für Dashboard, Kopfgelder und Dungeons.
Liest nur aus state und config, schreibt nichts.
"""
from datetime import datetime, timedelta
from collections import defaultdict
import state
import config


def _active_duration_ts(timestamps, threshold_min=None):
    """Wie _active_duration, aber direkt mit einer Liste von datetime-Objekten."""
    if threshold_min is None:
        threshold_min = config.PAUSE_THRESHOLD_MIN
    if len(timestamps) < 2:
        return 0.0
    active = 0.0
    for i in range(1, len(timestamps)):
        gap = (timestamps[i] - timestamps[i-1]).total_seconds() / 60
        if gap < threshold_min:
            active += gap
    return active


def _cutoff(period):
    now = datetime.now()
    if period == "hour":  return now - timedelta(hours=1)
    if period == "today": return now.replace(hour=0, minute=0, second=0, microsecond=0)
    if period == "week":  return now - timedelta(days=7)
    return datetime.min


def _active_duration(entries, threshold_min=None):
    """Berechnet aktive Spielzeit in Minuten (ignoriert lange Pausen)."""
    if threshold_min is None:
        threshold_min = config.PAUSE_THRESHOLD_MIN
    if len(entries) < 2:
        return 0.0
    active = 0.0
    for i in range(1, len(entries)):
        gap = (entries[i]["timestamp"] - entries[i-1]["timestamp"]).total_seconds() / 60
        if gap < threshold_min:
            active += gap
    return active


def compute_stats(period):
    """Haupt-Statistik für das Dashboard."""
    cutoff = _cutoff(period)
    with state.data_lock:
        filtered = [e for e in state.loot_entries if e["timestamp"] >= cutoff]
    if not filtered:
        return {
            "period": period, "total_yang": 0, "total_items": 0, "items": {},
            "yang_timeline": [], "session_start": None,
            "session_duration_min": 0, "active_duration_min": 0, "pause_duration_min": 0,
            "entry_count": 0, "yang_per_hour": 0, "dungeon_count": 0,
        }
    items, yang_by_hour = defaultdict(int), defaultdict(int)
    total_yang = 0
    for e in filtered:
        if e["item"] == "Yang":
            total_yang += e["amount"]
            yang_by_hour[e["timestamp"].strftime("%d.%m %H:00")] += e["amount"]
        else:
            items[e["item"]] += e["amount"]
    session_start   = filtered[0]["timestamp"]
    session_dur_min = max(1, int((filtered[-1]["timestamp"] - session_start).total_seconds() / 60))
    active_dur_min  = max(1, int(_active_duration(filtered)))
    pause_dur_min   = max(0, session_dur_min - active_dur_min)
    with state.data_lock:
        dungeon_count = len([e for e in state.dungeon_entries if e["timestamp"] >= cutoff])
    return {
        "period":               period,
        "total_yang":           total_yang,
        "total_items":          sum(items.values()),
        "items":                dict(sorted(items.items(), key=lambda x: x[1], reverse=True)),
        "yang_timeline":        [{"hour": k, "yang": v} for k, v in sorted(yang_by_hour.items())],
        "session_start":        session_start.isoformat(),
        "session_duration_min": session_dur_min,
        "active_duration_min":  active_dur_min,
        "pause_duration_min":   pause_dur_min,
        "entry_count":          len(filtered),
        "yang_per_hour":        int(total_yang / max(1, active_dur_min / 60)),
        "dungeon_count":        dungeon_count,
    }


def compute_kopfgeld_stats(period):
    """Statistik für die Kopfgelder-Seite."""
    cutoff        = _cutoff(period)
    kopfgeld_cost = state.cfg.get("kopfgeld_cost", 0)
    with state.data_lock:
        filtered = [e for e in state.kopfgeld_entries if e["timestamp"] >= cutoff]
        last_any = state.kopfgeld_entries[-1]["timestamp"].isoformat() if state.kopfgeld_entries else None
    by_day, by_hour = defaultdict(int), defaultdict(int)
    for e in filtered:
        by_day[e["timestamp"].strftime("%d.%m.%y")] += 1
        by_hour[e["timestamp"].strftime("%H:00")]    += 1
    last_in_period     = filtered[-1]["timestamp"].isoformat() if filtered else None
    total_cost         = len(filtered) * kopfgeld_cost
    with state.data_lock:
        loot_f = [e for e in state.loot_entries if e["timestamp"] >= cutoff]
    total_yang_kopf    = sum(e["amount"] for e in loot_f if e["item"] == "Yang")
    kopf_active_min    = max(1, int(_active_duration(filtered, threshold_min=30))) if len(filtered) >= 2 else 1
    yang_per_hour_kopf = int(total_yang_kopf / max(1, kopf_active_min / 60)) if total_yang_kopf > 0 else 0
    return {
        "period":                 period,
        "total":                  len(filtered),
        "timeline":               [{"day":  k, "count": v} for k, v in sorted(by_day.items())],
        "timeline_hour":          [{"hour": k, "count": v} for k, v in sorted(by_hour.items())],
        "last_timestamp":         last_in_period,
        "last_timestamp_any":     last_any,
        "watcher_active":         config.OCR_AVAILABLE,
        "kopfgeld_cost":          kopfgeld_cost,
        "total_cost":             total_cost,
        "yang_per_hour_kopfgeld": yang_per_hour_kopf,
        "kopf_active_min":        kopf_active_min,
    }


def compute_dungeon_stats(period):
    from collections import defaultdict as _dd
    cutoff     = _cutoff(period)
    configured = state.cfg.get("dungeons", [])
    with state.data_lock:
        filtered = [e for e in state.dungeon_entries if e["timestamp"] >= cutoff]
        loot_f   = [e for e in state.loot_entries   if e["timestamp"] >= cutoff]
    if not filtered:
        return {"period":period,"total_runs":0,"runs_per_hour":0,"dungeon_active_min":0,
                "yang_per_hour_dungeon":0,"total_cost":0,"avg_cost_per_run":0,"net_profit":0,
                "configured_dungeons":configured,"by_dungeon":[],"timeline_hour":[]}
    active_min = max(1, int(_active_duration(filtered, threshold_min=30)))
    total_yang = sum(e["amount"] for e in loot_f if e["item"] == "Yang")
    by_name    = _dd(lambda: {"runs":0,"cost":0})
    for e in filtered:
        n = e.get("dungeon_name","Unbekannt")
        by_name[n]["runs"] += 1
        by_name[n]["cost"] += e.get("cost",0)
    by_dungeon = [{"name":n,"runs":v["runs"],"cost":v["cost"]}
                  for n,v in sorted(by_name.items(), key=lambda x:x[1]["runs"], reverse=True)]
    total_cost = sum(e.get("cost",0) for e in filtered)
    by_hour    = _dd(int)
    for e in filtered: by_hour[e["timestamp"].strftime("%H:00")] += 1
    return {"period":period,"total_runs":len(filtered),
            "runs_per_hour":int(len(filtered)/max(1,active_min/60)),
            "dungeon_active_min":active_min,
            "yang_per_hour_dungeon":int(total_yang/max(1,active_min/60)) if total_yang else 0,
            "total_cost":total_cost,"avg_cost_per_run":int(total_cost/len(filtered)),
            "net_profit":total_yang-total_cost,"configured_dungeons":configured,
            "by_dungeon":by_dungeon,
            "timeline_hour":[{"hour":k,"count":v} for k,v in sorted(by_hour.items())]}
