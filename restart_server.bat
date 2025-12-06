@echo off
echo 正在重启 Flask 服务...
cd /d "%~dp0"

:: 查找并关闭占用5000端口的进程
echo 检查端口 5000...
netstat -ano | findstr ":5000" > temp_port.txt

:: 杀死Python进程
for /f "tokens=5" %%i in ('netstat -ano ^| findstr ":5000" ^| findstr /i "LISTENING"') do (
    echo 找到进程ID: %%i
    taskkill /PID %%i /F 2>nul
)
timeout /t 2 /nobreak >nul

:: 清理临时文件
del temp_port.txt 2>nul

:: 启动应用
echo 启动 Flask 应用...
start run.bat

:: 等待几秒钟后打开浏览器
timeout /t 8 /nobreak >nul
echo.
echo 正在打开浏览器...
start http://localhost:5000/admin/data-collect

exit
