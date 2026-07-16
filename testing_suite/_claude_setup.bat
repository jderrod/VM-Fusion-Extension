@echo off
rem One-time helper: copy the uploaded v22 workbook into testing_suite and dump its structure.
cd /d "%~dp0"

set "SRC=C:\Users\james.derrod\AppData\Roaming\Claude\local-agent-mode-sessions\6c97087b-872b-42e6-b12a-73d8a4e71342\35311fa9-d52f-4bdd-a23e-5fdd285275fd\local_b2d8adc2-9b72-4aac-b04e-ce81e47ff622\uploads\Panel inputs & outputs v22 macro_enabled 2026_07_09(1).xlsm"
set "DST=Panel inputs & outputs v22 macro_enabled 2026_07_09.xlsm"

echo Copying workbook... > _claude_setup_log.txt
copy /Y "%SRC%" "%DST%" >> _claude_setup_log.txt 2>&1

where python >nul 2>&1
if %errorlevel%==0 (
    python inspect_workbook.py >> _claude_setup_log.txt 2>&1
) else (
    py inspect_workbook.py >> _claude_setup_log.txt 2>&1
)

echo DONE >> _claude_setup_log.txt
