@echo off
chcp 65001 >nul
cd /d "%~dp0"
python export_project.py
