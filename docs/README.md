# Documentation

This folder contains user documentation for the Fusion 360 Manufacturing Pipeline.

## Files

- **user_guide.tex** - Complete LaTeX user guide (compile to PDF)
- **quick_reference.pdf** - Quick reference card (generated from LaTeX)

## Compiling the User Guide

### Requirements

- LaTeX distribution (e.g., MiKTeX, TeX Live)
- pdflatex compiler

### Compile to PDF

```bash
cd docs
pdflatex user_guide.tex
pdflatex user_guide.tex  # Run twice for table of contents
```

### Online Compilation

Upload `user_guide.tex` to [Overleaf](https://www.overleaf.com) for easy online compilation.

## Output

The compiled PDF will be: `user_guide.pdf`

Distribute this PDF to:
- IT Department (for installation and maintenance)
- Mechanical Engineering (for daily use and troubleshooting)
- Business Unit (for order submission and monitoring)
