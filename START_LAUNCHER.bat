@echo off
title Launcher
cd /d "%~dp0"
call check_and_run.bat launcher.py
pause
