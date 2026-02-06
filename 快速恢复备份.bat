@echo off
chcp 65001 >nul
title 原型生成器 - 快速恢复备份
cls
echo 正在启动备份恢复工具...
python restore_backup.py
if %errorlevel% neq 0 (
    echo.
    echo 运行出错！请检查是否已安装 Python。
    echo.
    pause
)
