@echo off
title Universal Downloader
cd /d "%~dp0"
call check_and_run.bat ytdlp_downloader_gui.py
pause
