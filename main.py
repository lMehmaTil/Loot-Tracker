"""
main.py – Einstiegspunkt: Daten laden, Threads starten, pywebview öffnen.
"""
import threading, time
import webview

import config
import state
import watcher
import server
import updater


def main():
    # Auf neue Version prüfen (kehrt sofort zurück wenn kein Update nötig)
    updater.check_and_update()

    # Daten initial laden
    watcher.load_log_file()
    watcher.load_kopfgeld_file()

    # Hintergrund-Threads starten
    threading.Thread(target=watcher.tail_log_file,        daemon=True).start()
    threading.Thread(target=watcher.tail_kopfgeld_file,   daemon=True).start()
    threading.Thread(target=watcher.run_kopfgeld_watcher, daemon=True).start()
    threading.Thread(target=server.run_flask,             daemon=True).start()

    # Zonen-Erkennung starten
    # Flask kurz Zeit geben, um zu starten
    time.sleep(1.0)

    # pywebview-Fenster erstellen
    api     = server.Api()
    win_cfg = state.cfg.get("window", {})
    win_w   = win_cfg.get("width",  1400)
    win_h   = win_cfg.get("height",  860)
    win_x   = win_cfg.get("x",     None)
    win_y   = win_cfg.get("y",     None)

    win_kwargs = dict(
        title      = "Nihor2 Loot Tracker",
        url        = "http://" + config.HOST + ":" + str(config.PORT),
        width      = win_w,
        height     = win_h,
        min_size   = (900, 600),
        resizable  = True,
        text_select= False,
        js_api     = api,
    )
    if win_x is not None:
        win_kwargs["x"] = win_x
    if win_y is not None:
        win_kwargs["y"] = win_y

    state.webview_window = webview.create_window(**win_kwargs)
    webview.start(debug=False)


if __name__ == "__main__":
    main()
