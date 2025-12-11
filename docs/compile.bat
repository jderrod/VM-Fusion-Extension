@echo off
echo ========================================
echo Compiling Fusion 360 Pipeline Documentation
echo ========================================
echo.

echo Compiling User Guide...
pdflatex -interaction=nonstopmode user_guide.tex
pdflatex -interaction=nonstopmode user_guide.tex

echo.
echo Compiling Quick Reference...
pdflatex -interaction=nonstopmode quick_reference.tex

echo.
echo Cleaning up auxiliary files...
del *.aux *.log *.toc *.out 2>nul

echo.
echo ========================================
echo Compilation Complete!
echo ========================================
echo.
echo Generated files:
echo   - user_guide.pdf
echo   - quick_reference.pdf
echo.
pause
