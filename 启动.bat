@echo off
chcp 65001 >nul
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
title 408考研AI助教
cd /d "%~dp0"
python start.py
pause
