@echo off
title HLS Downloader
cd /d "%~dp0"
echo Starting HLS Downloader...
call check_and_run.bat hls_downloader_gui.py
pause
