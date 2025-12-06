@echo off
echo ===========================
echo 启动政企智能舆情分析系统
echo ===========================
echo.

cd /d "%~dp0"

REM 查找并关闭占用5000端口的进程
echo 正在检查端口占用...
for /f "tokens=5" %%i in ('netstat -ano ^| findstr ":5000" ^| findstr /i "LISTENING"') do (
    echo 找到进程ID: %%i
    taskkill /PID %%i /F >nul 2>&1
)
timeout /t 3 /nobreak >nul

REM 设置Python路径
set PYTHONPATH=.:app

REM 激活虚拟环境并启动
echo 激活虚拟环境...
call venv\Scripts\activate.bat

if errorlevel 1 (
    echo 错误: 无法激活虚拟环境！
    pause
    exit /b 1
)

echo ✅ 虚拟环境已激活
echo Python版本:
python --version
echo.

REM 验证bs4可用
echo 验证BeautifulSoup4...
python -c "import bs4; print('✅ BeautifulSoup4 v' + bs4.__version__ + ' 正常')" 2>nul
if errorlevel 1 (
    echo ⚠️  BeautifulSoup4未安装，正在安装...
    pip install beautifulsoup4==4.12.2 requests==2.31.0 lxml==5.1.0
)

echo.
echo ===========================
echo 正在启动 Flask 应用...
echo ===========================
echo 访问地址: http://localhost:5000
echo 默认管理员: admin / admin123
echo.
echo 按 Ctrl+C 停止服务
echo.

python manage.py

pause
