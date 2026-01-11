@echo off
setlocal EnableDelayedExpansion

:: ============================================================================
:: VIDEO ENCODER TOOLS - AUTOMATED SETUP SCRIPT
:: This script checks and installs Python and all required dependencies
:: ============================================================================

title Video Encoder Tools - Setup

echo.
echo ============================================================
echo    VIDEO ENCODER TOOLS - AUTOMATED SETUP
echo ============================================================
echo.

:: Change to script directory
cd /d "%~dp0"

:: ============================================================================
:: STEP 1: Check for Python Installation
:: ============================================================================

echo [1/4] Checking for Python installation...

:: Try to find python
where python >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    for /f "tokens=*" %%i in ('python --version 2^>^&1') do set PYTHON_VERSION=%%i
    echo       Found: !PYTHON_VERSION!
    set PYTHON_CMD=python
    goto :pip_check
)

:: Try py launcher
where py >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    for /f "tokens=*" %%i in ('py --version 2^>^&1') do set PYTHON_VERSION=%%i
    echo       Found: !PYTHON_VERSION!
    set PYTHON_CMD=py
    goto :pip_check
)

:: Python not found - attempt to install
echo       Python not found! Attempting to install...
echo.

:: Check if winget is available
where winget >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Python is not installed and winget is not available.
    echo.
    echo Please install Python manually:
    echo   1. Go to https://www.python.org/downloads/
    echo   2. Download the latest Python 3.x version
    echo   3. Run the installer and CHECK "Add Python to PATH"
    echo   4. Re-run this script after installation
    echo.
    pause
    exit /b 1
)

:: Install Python using winget
echo       Installing Python via winget...
winget install -e --id Python.Python.3.12 --accept-source-agreements --accept-package-agreements

if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Failed to install Python automatically.
    echo Please install Python manually from https://www.python.org/downloads/
    pause
    exit /b 1
)

:: Refresh PATH
echo       Refreshing environment...
call refreshenv >nul 2>&1

:: Verify installation
where python >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [INFO] Python installed but PATH not updated in current session.
    echo        Please close this window and run the script again.
    echo.
    pause
    exit /b 0
)

set PYTHON_CMD=python
for /f "tokens=*" %%i in ('python --version 2^>^&1') do set PYTHON_VERSION=%%i
echo       Successfully installed: !PYTHON_VERSION!

:: ============================================================================
:: STEP 2: Check for pip
:: ============================================================================
:pip_check
echo.
echo [2/4] Checking for pip...

%PYTHON_CMD% -m pip --version >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo       pip not found. Installing pip...
    %PYTHON_CMD% -m ensurepip --upgrade
    if %ERRORLEVEL% NEQ 0 (
        echo [ERROR] Failed to install pip.
        pause
        exit /b 1
    )
)

for /f "tokens=*" %%i in ('%PYTHON_CMD% -m pip --version 2^>^&1') do set PIP_VERSION=%%i
echo       Found: !PIP_VERSION!

:: ============================================================================
:: STEP 3: Upgrade pip to latest version
:: ============================================================================
echo.
echo [3/4] Upgrading pip to latest version...
%PYTHON_CMD% -m pip install --upgrade pip --quiet
echo       Done.

:: ============================================================================
:: STEP 4: Install required packages
:: ============================================================================
echo.
echo [4/4] Installing required Python packages...
echo.

:: Check if requirements.txt exists
if not exist "%~dp0requirements.txt" (
    echo [ERROR] requirements.txt not found in %~dp0
    pause
    exit /b 1
)

:: Install packages from requirements.txt
%PYTHON_CMD% -m pip install -r "%~dp0requirements.txt" --quiet --disable-pip-version-check

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [WARNING] Some packages may have failed to install.
    echo          Trying individual package installation...
    echo.
    
    :: Install packages individually for better error handling
    for /f "usebackq tokens=*" %%p in ("%~dp0requirements.txt") do (
        echo       Installing %%p...
        %PYTHON_CMD% -m pip install %%p --quiet --disable-pip-version-check
    )
)

echo.
echo ============================================================
echo    SETUP COMPLETE!
echo ============================================================
echo.
echo All dependencies have been installed. You can now run any of
echo the application .bat files:
echo.
echo   - START_LAUNCHER.bat       (Main launcher)
echo   - START_ENCODER.bat        (Video encoder)
echo   - START_DOWNLOADER.bat     (HLS downloader)
echo   - START_UPLOADER.bat       (R2 uploader)
echo   - START_BULK_DOWNLOADER.bat
echo   - START_BULK_SPRITE_MAKER.bat
echo   - START_THUMBNAIL_MAKER.bat
echo   - START_UNIVERSAL_DOWNLOADER.bat
echo.
pause
exit /b 0
