@echo off
rem Launch the Fusion pipeline dashboard (requires Python 3 on PATH)
cd /d "%~dp0"
python pipeline_dashboard.py %*
pause
