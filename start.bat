@echo off
cd /d "%~dp0"
pip install flask pywebview -q --disable-pip-version-check
cmd /k "python loot_tracker.py"
