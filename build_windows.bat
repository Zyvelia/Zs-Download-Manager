@echo off
setlocal
cd /d "%~dp0"

echo Building Z's Download Manager for Windows...

rem Find the compiler before spending time building the executable.
set "ISCC="
for /f "usebackq delims=" %%I in (`powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\find-inno-setup.ps1"`) do if not defined ISCC set "ISCC=%%I"
if not defined ISCC (
    echo ERROR: Could not find Inno Setup 6 or 7. If installed in a custom location,
    echo set ISCC_PATH to the full path to ISCC.exe and rerun this script.
    echo Example: set "ISCC_PATH=C:\My Tools\Inno Setup 6\ISCC.exe"
    goto :fail
)
echo Using Inno Setup compiler: %ISCC%
rem Prefer a compatible existing 64-bit Python, including versions other than 3.12.
if exist ".venv-build\Scripts\python.exe" (
    ".venv-build\Scripts\python.exe" -c "import sys, struct; sys.exit(not (sys.version_info[:2] in [(3,10),(3,11),(3,12),(3,13)] and struct.calcsize('P') == 8))" >nul 2>&1
    if not errorlevel 1 goto :venv_ready
    echo ERROR: Existing .venv-build is incompatible or broken. Rename or delete that folder and try again.
    goto :fail
)
set "BASE_PYTHON="
where py >nul 2>&1
if errorlevel 1 goto :check_path_python
for %%V in (3.12 3.13 3.11 3.10) do (
    py -%%V-64 -c "import sys, struct; sys.exit(struct.calcsize('P') != 8)" >nul 2>&1
    if not errorlevel 1 (
        set "BASE_PYTHON=py -%%V-64"
        goto :create_venv
    )
)
:check_path_python
python -c "import sys, struct; sys.exit(not (sys.version_info[:2] in [(3,10),(3,11),(3,12),(3,13)] and struct.calcsize('P') == 8))" >nul 2>&1
if not errorlevel 1 (
    set "BASE_PYTHON=python"
    goto :create_venv
)
set "LOCAL_PYTHON=%LOCALAPPDATA%\NexusBuildTools\Python312\python.exe"
if exist "%LOCAL_PYTHON%" goto :use_local_python

echo No compatible 64-bit Python found. Downloading Python 3.12 from python.org...
echo Installing Python for this user only; this may take a few minutes.
set "PY_INSTALLER=%TEMP%\nexus-python-3.12.10-amd64.exe"
powershell -NoProfile -ExecutionPolicy Bypass -Command "$ErrorActionPreference='Stop'; [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -Uri 'https://www.python.org/ftp/python/3.12.10/python-3.12.10-amd64.exe' -OutFile $env:PY_INSTALLER"
if errorlevel 1 (
    echo ERROR: Could not download Python. Check your internet connection and try again.
    goto :fail
)
start "" /wait "%PY_INSTALLER%" /quiet InstallAllUsers=0 "TargetDir=%LOCALAPPDATA%\NexusBuildTools\Python312" Include_pip=1 Include_launcher=0 PrependPath=0
if errorlevel 1 (
    echo ERROR: The Python installer failed. Check the installer output and permissions.
    goto :fail
)
if not exist "%LOCAL_PYTHON%" (
    echo ERROR: Python installation did not produce the expected executable.
    goto :fail
)
:use_local_python
set "BASE_PYTHON="%LOCAL_PYTHON%""
:create_venv
echo Creating the build environment using %BASE_PYTHON%...
%BASE_PYTHON% -m venv .venv-build
if errorlevel 1 (
    echo ERROR: Could not create the Python build environment.
    goto :fail
)
:venv_ready
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

rem Package a separate console native-messaging host and copy it beside the app.
"%PYTHON%" -m PyInstaller --noconfirm --clean --console --onefile --name ZBrowserHost browser_host.py
if errorlevel 1 goto :fail
copy /y "dist\ZBrowserHost.exe" "dist\NexusDownloadManager\ZBrowserHost.exe" >nul
if errorlevel 1 goto :fail

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
