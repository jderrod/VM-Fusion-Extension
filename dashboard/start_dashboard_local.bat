@echo off
rem Launch the pipeline dashboard against the LOCAL sandbox instead of the
rem production shares. Mirrors the paths config.py uses in LOCAL mode.
rem
rem Start/Restart buttons stay ENABLED so the full launch-control loop can be
rem rehearsed locally. Pass --no-actions for a view-only dashboard that never
rem touches the Fusion process.
rem
rem NOTE: this file must keep CRLF line endings - cmd.exe mishandles LF-only
rem batch files.
setlocal
cd /d "%~dp0"
set "LOCAL_BASE=%~dp0..\local_test_env"
python pipeline_dashboard.py --data-dir "%LOCAL_BASE%\output\dashboard" --dropbox-dir "%LOCAL_BASE%\order_dropbox" %*
pause
