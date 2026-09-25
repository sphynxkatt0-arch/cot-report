@echo off
cd /d "%~dp0"
echo [%date% %time%] Refreshing and rebuilding the directional COT system...
py refresh_directional_cot_system.py --open
if not %errorlevel%==0 (
  echo [%date% %time%] ERROR: directional COT system refresh failed. Review model_output\directional_refresh_status.json and dashboard_refresh_logs.
  pause
  exit /b 1
)
echo [%date% %time%] Directional COT report and macro dashboard are ready.
