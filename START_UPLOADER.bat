@echo off
title R2 Uploader
cd /d "%~dp0"
call check_and_run.bat r2_uploader_gui.py
pause
