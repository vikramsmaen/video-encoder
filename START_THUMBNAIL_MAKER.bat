@echo off
title Thumbnail Maker
cd /d "%~dp0"
call check_and_run.bat thumbnail_maker.py
pause
