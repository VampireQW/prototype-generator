@echo off
setlocal
chcp 65001 >nul
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8:backslashreplace"
cd /d "%~dp0"
if errorlevel 1 goto failed

if exist ".venv\Scripts\python.exe" goto local_python
where py >nul 2>nul
if not errorlevel 1 goto python_launcher
where python >nul 2>nul
if not errorlevel 1 goto system_python
echo [ERROR] Python 3.10+ is required. Install Python from python.org and enable PATH.
goto failed

:local_python
".venv\Scripts\python.exe" -X utf8 launcher.py --open-browser %*
goto finished

:python_launcher
py -3 -X utf8 launcher.py --open-browser %*
goto finished

:system_python
python -X utf8 launcher.py --open-browser %*
goto finished

:finished
set "APP_EXIT=%errorlevel%"
if "%APP_EXIT%"=="0" exit /b 0
echo [ERROR] Startup failed. See the message above.
pause
exit /b %APP_EXIT%

:failed
pause
exit /b 1
