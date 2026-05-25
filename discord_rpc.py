"""
discord_rpc.py – Discord Rich Presence Proxy (Windows only).

Funktionsweise:
  Erstellt einen Named-Pipe-Server auf \\.\pipe\discord-ipc-N (auf dem
  ersten freien Slot). Das Spiel verbindet sich mit diesem Server statt
  mit Discord. Wir lesen die Rich-Presence-Frames, extrahieren die Zone
  und leiten alles transparent an die echte Discord-Pipe weiter.

WICHTIG: Damit das funktioniert muss dieser Prozess BEFORE Discord
         gestartet werden – oder Discord nutzt discord-ipc-1..9 und
         wir schnappen uns ipc-0.

Wenn pywin32 nicht installiert ist oder das Betriebssystem kein
Windows ist, deaktiviert sich dieses Modul automatisch.
"""
import struct, json, time, threading, sys

import state


# ── pywin32 optional laden ────────────────────────────────────────────────────

def _load_win32():
    if sys.platform != "win32":
        return None, None, None
    try:
        import win32pipe, win32file, pywintypes
        return win32pipe, win32file, pywintypes
    except ImportError:
        return None, None, None


# ── Discord IPC Protokoll ─────────────────────────────────────────────────────
# Opcodes: 0=HANDSHAKE  1=FRAME  2=CLOSE  3=PING  4=PONG

def _read_frame(handle, win32file):
    """Liest einen kompletten Discord-RPC-Frame aus der Pipe."""
    try:
        _, header = win32file.ReadFile(handle, 8)
        if len(header) < 8:
            return None, None
        op, length = struct.unpack("<II", header)
        payload = b""
        while len(payload) < length:
            _, chunk = win32file.ReadFile(handle, length - len(payload))
            payload += chunk
        return op, json.loads(payload.decode("utf-8", errors="replace"))
    except Exception:
        return None, None


def _write_frame(handle, op: int, data: dict, win32file):
    """Schreibt einen Discord-RPC-Frame in die Pipe."""
    try:
        payload = json.dumps(data).encode("utf-8")
        header  = struct.pack("<II", op, len(payload))
        win32file.WriteFile(handle, header + payload)
    except Exception:
        pass


# ── Zone aus Frame extrahieren ────────────────────────────────────────────────

def _extract_zone(data: dict) -> str | None:
    """
    Liest Zone-Informationen aus einem SET_ACTIVITY Frame.
    Prüft state → details → large_text (in dieser Reihenfolge).
    """
    if not isinstance(data, dict):
        return None
    if data.get("cmd") != "SET_ACTIVITY":
        return None
    activity = data.get("args", {}).get("activity", {})
    if not activity:
        return None

    candidates = [
        activity.get("state"),
        activity.get("details"),
        activity.get("assets", {}).get("large_text"),
        activity.get("assets", {}).get("small_text"),
    ]
    return next((c for c in candidates if c and len(c.strip()) > 1), None)


# ── Pipe Utilities ────────────────────────────────────────────────────────────

def _find_free_slot(win32file) -> int:
    """Gibt den ersten Slot zurück, auf dem KEIN Discord-Server läuft."""
    for i in range(10):
        pipe_name = f"\\\\.\\pipe\\discord-ipc-{i}"
        try:
            import win32con
            h = win32file.CreateFile(
                pipe_name,
                win32file.GENERIC_READ | win32file.GENERIC_WRITE,
                0, None,
                win32con.OPEN_EXISTING,
                0, None,
            )
            win32file.CloseHandle(h)
            # Verbindung gelungen → Discord-Server läuft hier bereits
        except Exception:
            # Verbindung fehlgeschlagen → Slot ist frei
            return i
    return -1


def _open_discord_pipe(win32file, win32con, skip_slot: int):
    """Öffnet die erste verfügbare echte Discord-Pipe (außer skip_slot)."""
    for i in range(10):
        if i == skip_slot:
            continue
        pipe_name = f"\\\\.\\pipe\\discord-ipc-{i}"
        try:
            h = win32file.CreateFile(
                pipe_name,
                win32file.GENERIC_READ | win32file.GENERIC_WRITE,
                0, None,
                win32con.OPEN_EXISTING,
                0, None,
            )
            return h, i
        except Exception:
            continue
    return None, -1


def _create_server(win32pipe, win32file, slot: int):
    pipe_name = f"\\\\.\\pipe\\discord-ipc-{slot}"
    try:
        return win32pipe.CreateNamedPipe(
            pipe_name,
            win32pipe.PIPE_ACCESS_DUPLEX,
            win32pipe.PIPE_TYPE_BYTE | win32pipe.PIPE_READMODE_BYTE | win32pipe.PIPE_WAIT,
            win32pipe.PIPE_UNLIMITED_INSTANCES,
            65536, 65536,
            0, None,
        )
    except Exception as e:
        print(f"[Discord RPC] Pipe erstellen fehlgeschlagen: {e}")
        return None


# ── Verbindungs-Handler ───────────────────────────────────────────────────────

def _handle_connection(server_handle, slot: int, win32pipe, win32file):
    """Verwaltet eine einzelne Spiel-Verbindung inkl. Discord-Weiterleitung."""
    import win32con
    discord_handle = None

    try:
        # Warte auf Verbindung vom Spiel (blockiert bis Spiel sich verbindet)
        win32pipe.ConnectNamedPipe(server_handle, None)
        print("[Discord RPC] Spiel verbunden!")

        # Echte Discord-Pipe öffnen
        discord_handle, d_slot = _open_discord_pipe(win32file, win32con, slot)
        if discord_handle:
            print(f"[Discord RPC] Discord-Weiterleitung auf ipc-{d_slot} aktiv.")
        else:
            print("[Discord RPC] Discord nicht gefunden – nur Zone-Erkennung aktiv.")

        while True:
            op, data = _read_frame(server_handle, win32file)
            if op is None:
                break

            # Zone extrahieren und State aktualisieren
            zone = _extract_zone(data)
            if zone:
                with state.data_lock:
                    state.current_zone = zone
                print(f"[Discord RPC] Zone: {zone}")
                try:
                    import watcher as w
                    import json as _j
                    w._notify(_j.dumps({"type": "zone", "zone": zone, "signature": ""}))
                except Exception:
                    pass

            # An echtes Discord weiterleiten
            if discord_handle:
                _write_frame(discord_handle, op, data, win32file)
                # Antwort von Discord zurück an Spiel
                r_op, r_data = _read_frame(discord_handle, win32file)
                if r_op is not None:
                    _write_frame(server_handle, r_op, r_data, win32file)

    except Exception as e:
        print(f"[Discord RPC] Verbindungsfehler: {e}")
    finally:
        if discord_handle:
            try:
                win32file.CloseHandle(discord_handle)
            except Exception:
                pass
        try:
            win32pipe.DisconnectNamedPipe(server_handle)
        except Exception:
            pass


# ── Haupt-Loop ────────────────────────────────────────────────────────────────

def run_discord_rpc_proxy():
    """
    Startet den Discord-RPC-Proxy. Läuft als Endlos-Loop um nach
    jeder Verbindung wieder auf das Spiel zu warten.
    """
    win32pipe, win32file, pywintypes = _load_win32()
    if not win32pipe:
        print("[Discord RPC] Nicht verfügbar (kein Windows / pywin32 fehlt).")
        return

    import win32con
    slot = _find_free_slot(win32file)
    if slot == -1:
        print("[Discord RPC] Alle Pipe-Slots belegt – Proxy deaktiviert.")
        return

    print(f"[Discord RPC] Proxy gestartet auf discord-ipc-{slot}.")

    while True:
        server = _create_server(win32pipe, win32file, slot)
        if not server:
            time.sleep(5)
            continue
        try:
            _handle_connection(server, slot, win32pipe, win32file)
        finally:
            try:
                win32file.CloseHandle(server)
            except Exception:
                pass
