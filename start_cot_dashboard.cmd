@echo off
cd /d "%~dp0"
echo [%date% %time%] Starting integrated COT directional and macro refresh...
py refresh_directional_cot_system.py
if not %errorlevel%==0 (
  echo [%date% %time%] WARNING: integrated refresh failed; opening the latest existing dashboard if available.
) else (
  echo [%date% %time%] Integrated refresh completed successfully.
)
powershell -NoProfile -ExecutionPolicy Bypass -Command "$u='http://127.0.0.1:8765/interactive_cot_dashboard.html'; try { $r=Invoke-WebRequest -Uri $u -UseBasicParsing -TimeoutSec 2; $body=[string]$r.Content; if ($body.Contains('COT Macro Monitor') -and $body.Contains('directionalDecisionSummary')) { exit 0 }; exit 1 } catch { exit 1 }"
if %errorlevel%==0 (
  echo [%date% %time%] Existing integrated dashboard server found; opening http://127.0.0.1:8765/
  start "" "http://127.0.0.1:8765/"
) else (
  echo [%date% %time%] Starting dashboard server on 127.0.0.1:8765. If occupied, a free port will be selected.
  py serve_interactive_cot_dashboard.py --skip-refresh --host 127.0.0.1 --port 8765 --open
)
echo [%date% %time%] start_cot_dashboard.cmd finished.
pause
