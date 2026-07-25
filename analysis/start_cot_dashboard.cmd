@echo off
cd /d "%~dp0"
echo [%date% %time%] Starting COT dashboard full refresh...
py serve_interactive_cot_dashboard.py --refresh-only
if not %errorlevel%==0 (
  echo [%date% %time%] WARNING: refresh failed; opening the existing dashboard file.
) else (
  echo [%date% %time%] Refresh command completed successfully.
)
powershell -NoProfile -ExecutionPolicy Bypass -Command "$u='http://127.0.0.1:8765/interactive_cot_dashboard.html'; try { $r=Invoke-WebRequest -Uri $u -UseBasicParsing -TimeoutSec 2; $body=[string]$r.Content; if ($body.Contains('COT Macro Monitor') -and $body.Contains('summaryStrip')) { exit 0 }; exit 1 } catch { exit 1 }"
if %errorlevel%==0 (
  echo [%date% %time%] Existing dashboard server found; opening http://127.0.0.1:8765/
  start "" "http://127.0.0.1:8765/"
) else (
  echo [%date% %time%] No COT dashboard server found on 127.0.0.1:8765; starting dashboard server. If that port is busy, a free port will be used.
  py serve_interactive_cot_dashboard.py --skip-refresh --host 127.0.0.1 --port 8765 --open
)
echo [%date% %time%] start_cot_dashboard.cmd finished.
pause
