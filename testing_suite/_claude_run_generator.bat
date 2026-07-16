@echo off
rem Helper: dump Panel Calculated Values formulas.
cd /d "%~dp0"

where python >nul 2>&1
if %errorlevel%==0 (
    python _claude_dump_formulas.py > _claude_gen_log.txt 2>&1
) else (
    py _claude_dump_formulas.py > _claude_gen_log.txt 2>&1
)

echo EXITCODE %errorlevel% >> _claude_gen_log.txt
echo DONE >> _claude_gen_log.txt
