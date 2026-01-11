@echo off
setlocal EnableDelayedExpansion

:: ============================================================================
:: Helper script that checks dependencies before running any Python script
:: Usage: call check_and_run.bat <python_script.py>
:: ============================================================================

cd /d "%~dp0"

:: Get the Python script name from argument
set SCRIPT_NAME=%~1

if "%SCRIPT_NAME%"=="" (
    echo [ERROR] No script specified.
    pause
    exit /b 1
)

:: Quick check if Python is available
where python >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    set PYTHON_CMD=python
    goto :check_deps
)

where py >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    set PYTHON_CMD=py
    goto :check_deps
)

:: Python not found - run setup
echo.
echo Python not found. Running first-time setup...
echo.
call "%~dp0setup.bat"
if %ERRORLEVEL% NEQ 0 (
    exit /b 1
)

:: Re-check for Python after setup
where python >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    set PYTHON_CMD=python
    goto :check_deps
)

where py >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    set PYTHON_CMD=py
    goto :check_deps
)

echo [ERROR] Python still not available after setup.
echo Please restart your computer and try again.
pause
exit /b 1

:check_deps
:: Check if key packages are installed (quick check)
%PYTHON_CMD% -c "import boto3, watchdog, dotenv, requests, m3u8, yt_dlp" >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo Some dependencies are missing. Installing required packages...
    echo.
    %PYTHON_CMD% -m pip install -r "%~dp0requirements.txt" --quiet --disable-pip-version-check
    if %ERRORLEVEL% NEQ 0 (
        echo.
        echo [WARNING] Failed to install some packages. Running full setup...
        call "%~dp0setup.bat"
    )
)

:: Run the requested Python script
echo.
%PYTHON_CMD% "%~dp0%SCRIPT_NAME%"
exit /b %ERRORLEVEL%
