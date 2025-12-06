@echo off
chcp 65001 > nul
echo 正在启动政企智能舆情分析系统...
echo 使用虚拟环境Python...

cd /d "%~dp0"
call venv\Scripts\activate.bat

if errorlevel 1 (
    echo 错误: 无法激活虚拟环境！
    pause
    exit /b 1
)

echo 已激活虚拟环境
echo Python版本:
python --version
echo.

REM 检查bs4模块
python -c "import bs4; print('BeautifulSoup4 已安装: v' + bs4.__version__)" 2>nul
if errorlevel 1 (
    echo 警告: BeautifulSoup4未安装，正在安装...
    pip install beautifulsoup4==4.12.2
)

REM 检查其他依赖
python -c "import requests; print('Requests 已安装')" 2>nul
if errorlevel 1 (
    echo 警告: Requests未安装，正在安装...
    pip install requests==2.31.0
)

echo.
echo [OK] 所有依赖已检查完毕
echo.
echo 正在启动 Flask 应用...
echo 访问地址: http://localhost:5000
echo 默认管理员: admin / admin123
echo.
echo 按 Ctrl+C 退出
python manage.py

pause
