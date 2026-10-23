@echo off
:: 1. 进入当前脚本所在目录
cd /d "%~dp0"

echo [INFO] 正在启动服务...

:: 2. 服务完成交接并启动成功后打开浏览器
python server.py --open-browser
if errorlevel 1 (
    pause
    exit /b 1
)
exit /b 0
