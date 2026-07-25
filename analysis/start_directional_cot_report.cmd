@echo off
cd /d "%~dp0"
echo [%date% %time%] Refreshing COT and macro data...
py serve_interactive_cot_dashboard.py --refresh-only
if not %errorlevel%==0 (
  echo [%date% %time%] WARNING: refresh failed; attempting to use the latest cached outputs.
)
echo [%date% %time%] Building directional COT report...
py build_directional_cot_report.py
if not %errorlevel%==0 (
  echo [%date% %time%] ERROR: directional report build failed.
  pause
  exit /b 1
)
start "" "%~dp0directional_cot_report.html"
echo [%date% %time%] Opened decision-first COT report.
