@echo off
setlocal
title GpuTempFloat - build exe

set "PY=C:\Users\27716\AppData\Local\Programs\Python\Python312\python.exe"
set "HERE=%~dp0"
set "APPNAME=GpuTempFloat"
set "BUILDVENV=%LOCALAPPDATA%\GpuTempFloat\buildenv"
set "UPXDIR=%HERE%tools\upx"
set "PIPMIRROR=https://repo.huaweicloud.com/repository/pypi/simple"

echo ==================================================
echo  GpuTempFloat : single-file exe build (slim + UPX)
echo  source: %HERE%gpu_temp_float.py
echo ==================================================

echo.
echo [1/5] check python ...
if exist "%PY%" goto :havepy
set "PY=python"
where python >nul 2>nul
if errorlevel 1 goto :fail_py

:havepy
echo        using: %PY%

echo.
echo [2/5] prepare build venv: %BUILDVENV%
if exist "%BUILDVENV%\Scripts\python.exe" goto :havevenv
"%PY%" -m venv "%BUILDVENV%"
if errorlevel 1 goto :fail_venv

:havevenv
echo        venv ok

echo.
echo [3/5] install PySide6-Essentials + PyInstaller (mirror: huaweicloud) ...
"%BUILDVENV%\Scripts\python.exe" -m pip install --upgrade pip -i %PIPMIRROR% >nul 2>nul
"%BUILDVENV%\Scripts\python.exe" -m pip install "PySide6-Essentials==6.9.1" pyinstaller -i %PIPMIRROR%
if errorlevel 1 goto :fail_pip

echo.
echo [4/5] prepare icon + upx ...
if exist "%HERE%assets\app.ico" goto :haveico
"%BUILDVENV%\Scripts\python.exe" "%HERE%make_icon.py"
if errorlevel 1 goto :fail_icon

:haveico
echo        icon ok
if exist "%UPXDIR%\upx.exe" goto :haveupx
echo        upx missing, try download ...
if not exist "%UPXDIR%" mkdir "%UPXDIR%"
curl -L -o "%TEMP%\upx.zip" "https://github.com/upx/upx/releases/download/v4.2.4/upx-4.2.4-win64.zip"
if not exist "%TEMP%\upx.zip" echo        upx download failed, build WITHOUT upx ^(bigger exe^)
if not exist "%TEMP%\upx.zip" goto :haveupx
powershell -NoProfile -Command "Expand-Archive -Path '%TEMP%\upx.zip' -DestinationPath '%TEMP%\upx_x' -Force" >nul 2>nul
xcopy /y /q /e "%TEMP%\upx_x\upx-4.2.4-win64\*" "%UPXDIR%\" >nul 2>nul
del /q "%TEMP%\upx.zip" >nul 2>nul

:haveupx
echo        upx dir: %UPXDIR%

echo.
echo [5/5] run PyInstaller with GpuTempFloat.spec ...
cd /d "%HERE%"
set "UPX_DIR=%UPXDIR%"
"%BUILDVENV%\Scripts\python.exe" -m PyInstaller --noconfirm --clean --distpath "%HERE%dist" --workpath "%HERE%build" "%HERE%GpuTempFloat.spec"
if errorlevel 1 goto :fail_build
if not exist "%HERE%dist\%APPNAME%.exe" goto :fail_build

copy /y "%HERE%dist\%APPNAME%.exe" "%HERE%%APPNAME%.exe" >nul
echo.
echo ==================================================
echo  BUILD OK
for %%F in ("%HERE%%APPNAME%.exe") do echo  exe : %%~fF
for %%F in ("%HERE%%APPNAME%.exe") do echo  size: %%~zF bytes
echo  trimmed Qt runtime (no OpenGL-SW / Network / SVG / image plugins) + UPX
echo ==================================================
echo.
pause
exit /b 0

:fail_py
echo [ERROR] python not found. Install Python 3.12 and retry.
goto :die

:fail_venv
echo [ERROR] cannot create venv at %BUILDVENV%
goto :die

:fail_pip
echo [ERROR] pip install failed. Check network / proxy.
goto :die

:fail_icon
echo [ERROR] icon build failed (make_icon.py).
goto :die

:fail_build
echo [ERROR] PyInstaller failed. See build\GpuTempFloat\warn-GpuTempFloat.txt.
goto :die

:die
echo.
pause
exit /b 1
