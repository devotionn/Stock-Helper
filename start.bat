@echo off
chcp 65001 >nul
title 股票分析助手
cd /d "%~dp0backend"
python run.py
pause
