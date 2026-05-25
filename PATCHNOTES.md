# Loot Tracker – Patchnotes

---

## v1.1 – Auto-Updater
*25. Mai 2026*

### Neu
- **Automatischer Update-Check beim Start** – Der Loot Tracker prüft beim Öffnen ob eine neue Version verfügbar ist.
- **Fortschrittsbalken-Fenster** – Wird ein Update gefunden, erscheint ein Fenster das den Download- und Installationsfortschritt anzeigt.
- **Sicheres Update** – Nur die Programmdateien werden aktualisiert (`LootTracker.exe`, `dashboard.html`, `icons/`). Deine persönliche Konfiguration (`config.json`) und deine Log-Dateien bleiben vollständig erhalten.
- **Automatischer Neustart** – Nach dem Update startet der Loot Tracker automatisch mit der neuen Version neu.

### Hinweis
Dieses Update muss einmalig manuell installiert werden. Ab v1.1 laufen alle zukünftigen Updates automatisch.

---

## v1.0 – Erster Release
*24. Mai 2026*

### Features
- Live-Dashboard im Browser mit Drop-Statistiken
- Automatisches Einlesen der Metin2 Log-Datei
- Item-Tracking mit Icons und Kategorien
- Kopfgeld-Tracking
- Discord Rich Presence (RPC)
- Konfigurierbare Einstellungen via `config.json`
