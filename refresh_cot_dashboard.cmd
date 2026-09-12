@echo off
cd /d "%~dp0"
py refresh_directional_cot_system.py
if not %errorlevel%==0 (
  echo Integrated directional refresh failed. Review model_output\directional_refresh_status.json and dashboard_refresh_logs.
)
pause
