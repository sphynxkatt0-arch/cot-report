@echo off
cd /d "%~dp0"
py serve_interactive_cot_dashboard.py --refresh-only
pause
