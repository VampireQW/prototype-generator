@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo 为现有项目注入页面导航监听器...
echo.
python inject_listener.py
