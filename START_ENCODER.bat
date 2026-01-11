@echo off
title Video Encoder
cd /d "%~dp0"
call check_and_run.bat video_encoder.py
pause
