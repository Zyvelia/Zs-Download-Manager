@echo off
setlocal
cd /d "%~dp0"

echo Building NEXUS for Windows...
where py >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python launcher not found. Install 64-bit Python 3.12 from python.org.
    goto :fail
)
if not exist ".venv-build\Scripts\python.exe" (
    py -3.12 -m venv .venv-build
    if errorlevel 1 goto :fail
)
set "PYTHON=%CD%\.venv-build\Scripts\python.exe"
"%PYTHON%" -m pip install --upgrade pip
if errorlevel 1 goto :fail
"%PYTHON%" -m pip install -r requirements.txt "pyinstaller>=6,<7"
if errorlevel 1 goto :fail
"%PYTHON%" -c "import PySide6, libtorrent; print('Dependencies OK')"
if errorlevel 1 goto :fail

rem Use a directory bundle so the Qt and libtorrent runtime files travel with the executable.
"%PYTHON%" -m PyInstaller --noconfirm --clean --windowed --onedir --name NexusDownloadManager --icon "assets\logo.ico" --add-data "assets;assets" --collect-all libtorrent main.py
if errorlevel 1 goto :fail
if not exist "dist\NexusDownloadManager\NexusDownloadManager.exe" goto :fail

rem ISCC can be on PATH or in the standard Inno Setup 6 installation directory.
set "ISCC="
for /f "delims=" %%I in ('where ISCC.exe 2^>nul') do if not defined ISCC set "ISCC=%%I"
if not defined ISCC if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if not defined ISCC if exist "%ProgramFiles%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe"
if not defined ISCC (
    echo ERROR: Inno Setup 6 compiler ISCC.exe was not found. Install Inno Setup 6 and run this script again.
    goto :fail
)
"%ISCC%" "installer.iss"
if errorlevel 1 goto :fail

echo.
echo SUCCESS: executable folder: dist\NexusDownloadManager
echo SUCCESS: installer: installer-output\NexusDownloadManager-Setup.exe
if /i not "%~1"=="--no-pause" pause
exit /b 0

:fail
echo.
echo Build failed. Review the error above.
echo If you need help, copy the error text or take a screenshot.
if /i not "%~1"=="--no-pause" pause
exit /b 1
