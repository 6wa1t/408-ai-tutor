@echo off
chcp 65001 >nul
title 408考研AI助教
cd /d "%~dp0"
python start.py
pause
