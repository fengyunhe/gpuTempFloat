@echo off
rem ASCII-only launcher (cmd codepage safe)
set "VENV=%LOCALAPPDATA%\GpuTempFloat\venv"
if exist "%VENV%\Scripts\pythonw.exe" goto run
echo [!] Python env not found. Run "install_deps.bat" first.
pause
exit /b 1
:run
start "" "%VENV%\Scripts\pythonw.exe" "%~dp0gpu_temp_float.py"
exit
