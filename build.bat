@echo off
title Loot Tracker - Build EXE
color 0B
cd /d "%~dp0"

echo.
echo  ============================================
echo   Loot Tracker - EXE Build
echo  ============================================
echo.

:: Abhängigkeiten installieren
echo  [1/2] Installiere Pakete...
pip install pyinstaller flask pywebview pytesseract mss pywin32 Pillow requests
echo.

:: Altes Build aufräumen
if exist "dist"  rmdir /s /q "dist"
if exist "build" rmdir /s /q "build"
if exist "LootTracker.spec" del "LootTracker.spec"

:: EXE bauen - voller Output sichtbar
echo  [2/2] Baue LootTracker.exe...
echo  (Kann 1-3 Minuten dauern, bitte warten...)
echo.
pyinstaller --onefile --noconsole --name "LootTracker" ^
    --hidden-import "webview.platforms.winforms" ^
    --hidden-import "win32pipe" ^
    --hidden-import "win32file" ^
    --hidden-import "win32con" ^
    --hidden-import "pywintypes" ^
    --hidden-import "tkinter" ^
    --hidden-import "tkinter.ttk" ^
    --collect-all "webview" ^
    --collect-all "requests" ^
    --collect-all "urllib3" ^
    --collect-all "charset_normalizer" ^
    --collect-all "certifi" ^
    main.py

echo.
if exist "dist\LootTracker.exe" (
    copy "dashboard.html" "dist\" >nul
    copy "version.txt" "dist\" >nul
    copy "latest_version.txt" "dist\" >nul
    if not exist "dist\kopfgelder.log" type nul > "dist\kopfgelder.log"
    if not exist "dist\icons" mkdir "dist\icons"
    if exist "icons" xcopy /e /i /q "icons" "dist\icons" >nul
    rmdir /s /q "build" 2>nul
    del "LootTracker.spec" 2>nul
    echo  ============================================
    echo   FERTIG! dist\LootTracker.exe erstellt.
    echo  ============================================
    explorer "dist"
) else (
    echo  ============================================
    echo   BUILD FEHLGESCHLAGEN!
    echo   Lies die Fehlermeldung oben genau durch
    echo   und schick sie an Claude.
    echo  ============================================
)
echo.
pause
