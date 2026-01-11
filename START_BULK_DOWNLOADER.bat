@echo off
title Bulk Video Downloader
cd /d "%~dp0"
call check_and_run.bat bulk_video_downloader.py
pause
