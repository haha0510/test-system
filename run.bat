@echo off
chcp 65001 >nul
title 政企智能舆情分析系统 [快速启动]

echo.
echo  正在启动系统...
echo  访问地址: http://localhost:5000
echo.

call venv\Scripts\activate.bat
python manage.py
