@echo off
rem Launch the Testing Suite Viewer (no console window).
cd /d "%~dp0"
start "" pythonw test_viewer.py
