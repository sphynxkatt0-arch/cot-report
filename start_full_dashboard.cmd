@echo off
setlocal
cd /d "%~dp0"
title COT Intelligence & Macro Direction Dashboard

echo ==============================================================================
echo Launching COT Intelligence Auto-Fetch, Build and Local Server...
echo ==============================================================================

py start_full_dashboard.py %*

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo Dashboard launch encountered an error.
    pause
)
