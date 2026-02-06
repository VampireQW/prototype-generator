@echo off
:: Simple wrapper for the Python splitter script
echo Starting Modao Splitter...
echo.

python "%~dp0split_to_modao.py" %*

if errorlevel 1 (
    echo.
    echo Script execution failed. Please check the error above.
    echo Ensure Python is installed and added to PATH.
)

echo.
pause
