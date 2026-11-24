@echo off
rem ASCII-only installer (cmd codepage safe)
set "PY=C:\Users\27716\AppData\Local\Programs\Python\Python312\python.exe"
set "VENV=%LOCALAPPDATA%\GpuTempFloat\venv"

if exist "%PY%" goto havepy
echo [!] Python 3.12 not found: %PY%
echo     Edit the PY variable in this script to your python.exe path.
pause
exit /b 1

:havepy
if exist "%VENV%\Scripts\python.exe" goto havevenv
echo [*] Creating virtualenv...
"%PY%" -m venv "%VENV%"

:havevenv
echo [*] Installing PySide6-Essentials (about 80MB, first run only)...
"%VENV%\Scripts\python.exe" -m pip install -U pip
"%VENV%\Scripts\python.exe" -m pip install "PySide6-Essentials==6.9.1"

echo.
echo [OK] Done. Double-click the launcher bat to start.
pause
