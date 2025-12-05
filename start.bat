@echo off
chcp 65001 >nul
title 政企智能舆情分析系统

echo ========================================
echo    政企智能舆情分析系统 启动脚本
echo ========================================
echo.

:: 检查虚拟环境
if not exist "venv\Scripts\activate.bat" (
    echo [错误] 未找到虚拟环境，正在创建...
    python -m venv venv
    if errorlevel 1 (
        echo [错误] 创建虚拟环境失败，请确保已安装Python
        pause
        exit /b 1
    )
    echo [成功] 虚拟环境创建完成
)

:: 激活虚拟环境
echo [1/3] 激活虚拟环境...
call venv\Scripts\activate.bat

:: 安装依赖
echo [2/3] 检查依赖...
pip install -r requirements.txt -q

:: 启动应用
echo [3/3] 启动应用...
echo.
echo ========================================
echo    访问地址: http://localhost:5000
echo    默认账户: admin / admin123
echo    按 Ctrl+C 停止服务
echo ========================================
echo.

python manage.py

pause
