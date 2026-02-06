# AI Prototype Generator - Startup Script

$pythonPath = "C:\python.exe"
$scriptPath = Join-Path $PSScriptRoot "server.py"

Write-Host "===================================================" -ForegroundColor Cyan
Write-Host "       AI Prototype Generator - Local Server" -ForegroundColor Cyan
Write-Host "==================================================="
Write-Host ""

if (-not (Test-Path $pythonPath)) {
    Write-Host "[ERROR] C:\python.exe not found." -ForegroundColor Red
    Write-Host "Please ensure Python is installed."
    Read-Host "Press Enter to exit"
    exit
}

Write-Host "[INFO] Starting server..." -ForegroundColor Green
Write-Host "Target: $scriptPath" -ForegroundColor Gray
Write-Host ""
Write-Host "Access URL: http://localhost:8080/src/index.html" -ForegroundColor Yellow
Write-Host ""

& $pythonPath $scriptPath

Read-Host "Press Enter to exit"
