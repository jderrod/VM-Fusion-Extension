# Setup Inputs Folder for Fusion Extension
# This script creates the inputs folder structure for persistent model storage

$ErrorActionPreference = "Stop"

Write-Host "==========================================" -ForegroundColor Cyan
Write-Host " Fusion Extension - Inputs Folder Setup" -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host ""

# Get script directory (repo root)
$repoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$inputsFolder = Join-Path $repoRoot "inputs"

Write-Host "Repository root: $repoRoot" -ForegroundColor Yellow
Write-Host "Inputs folder: $inputsFolder" -ForegroundColor Yellow
Write-Host ""

# Create main inputs folder
if (-not (Test-Path $inputsFolder)) {
    New-Item -Path $inputsFolder -ItemType Directory -Force | Out-Null
    Write-Host "[OK] Created inputs folder" -ForegroundColor Green
} else {
    Write-Host "[..] Inputs folder already exists" -ForegroundColor Gray
}

# Create subfolders for each component type
$componentTypes = @("door", "panel", "stile")

foreach ($type in $componentTypes) {
    $subfolder = Join-Path $inputsFolder $type
    if (-not (Test-Path $subfolder)) {
        New-Item -Path $subfolder -ItemType Directory -Force | Out-Null
        Write-Host "[OK] Created $type subfolder" -ForegroundColor Green
    } else {
        Write-Host "[..] $type subfolder already exists" -ForegroundColor Gray
    }
    
    # Check if any .f3d files exist
    $f3dFiles = Get-ChildItem -Path $subfolder -Filter "*.f3d" -ErrorAction SilentlyContinue
    if ($f3dFiles.Count -gt 0) {
        Write-Host "    Found model: $($f3dFiles[0].Name)" -ForegroundColor Cyan
    } else {
        Write-Host "    No .f3d model found - please add one" -ForegroundColor Yellow
    }
}

Write-Host ""
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host " Setup Complete!" -ForegroundColor Green
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Next steps:" -ForegroundColor Yellow
Write-Host "  1. Place your .f3d model files in the appropriate subfolders:" -ForegroundColor White
Write-Host "     - Door model  -> inputs/door/" -ForegroundColor White
Write-Host "     - Panel model -> inputs/panel/" -ForegroundColor White
Write-Host "     - Stile model -> inputs/stile/" -ForegroundColor White
Write-Host ""
Write-Host "  2. Ensure each model has user parameters that match your JSON" -ForegroundColor White
Write-Host ""
Write-Host "  3. See docs/INPUTS_FOLDER_SETUP.md for detailed instructions" -ForegroundColor White
Write-Host ""

# Show current status
Write-Host "Current Status:" -ForegroundColor Yellow
$allModelsPresent = $true

foreach ($type in $componentTypes) {
    $subfolder = Join-Path $inputsFolder $type
    $f3dFiles = Get-ChildItem -Path $subfolder -Filter "*.f3d" -ErrorAction SilentlyContinue
    
    if ($f3dFiles.Count -gt 0) {
        $status = "[OK] Ready"
        $color = "Green"
    } else {
        $status = "[!!] Missing .f3d file"
        $color = "Yellow"
        $allModelsPresent = $false
    }
    
    Write-Host "  $type : " -NoNewline -ForegroundColor White
    Write-Host $status -ForegroundColor $color
}

Write-Host ""

if ($allModelsPresent) {
    Write-Host "All models are configured! Ready to process orders." -ForegroundColor Green
} else {
    Write-Host "Please add missing .f3d model files to continue." -ForegroundColor Yellow
}

Write-Host ""
