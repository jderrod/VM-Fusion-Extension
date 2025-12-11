# Setup Auto-Run Order Processing
# Creates folders and installs dependencies

$ErrorActionPreference = "Stop"

Write-Host "==========================================" -ForegroundColor Cyan
Write-Host " Auto-Run Order Processing Setup" -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host ""

# Get script directory
$repoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path

Write-Host "Setting up automated order processing..." -ForegroundColor Yellow
Write-Host "Repository: $repoRoot" -ForegroundColor Gray
Write-Host ""

# Create folders
$folders = @(
    "order_dropbox",
    "order_processing",
    "order_completed",
    "order_failed"
)

Write-Host "Creating folders..." -ForegroundColor Yellow
foreach ($folder in $folders) {
    $path = Join-Path $repoRoot $folder
    if (-not (Test-Path $path)) {
        New-Item -Path $path -ItemType Directory -Force | Out-Null
        Write-Host "  [OK] $folder" -ForegroundColor Green
    } else {
        Write-Host "  [..] $folder (exists)" -ForegroundColor Gray
    }
}

Write-Host ""

# Check Python
Write-Host "Checking Python installation..." -ForegroundColor Yellow
try {
    $pythonTest = python --version 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-Host "  [OK] $pythonTest" -ForegroundColor Green
    } else {
        Write-Host "  [!!] Python not found - please install Python 3.7+" -ForegroundColor Red
    }
} catch {
    Write-Host "  [!!] Python not found - please install Python 3.7+" -ForegroundColor Red
}

Write-Host ""
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host " Setup Complete!" -ForegroundColor Green
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host ""

Write-Host "Folder Structure:" -ForegroundColor Yellow
Write-Host "  order_dropbox/     <- Drop new JSON orders here" -ForegroundColor White
Write-Host "  order_processing/  <- Currently processing" -ForegroundColor White
Write-Host "  order_completed/   <- Successfully completed" -ForegroundColor White
Write-Host "  order_failed/      <- Failed orders with error logs" -ForegroundColor White
Write-Host ""

Write-Host "Next Steps:" -ForegroundColor Yellow
Write-Host "  1. Configure models in inputs/ folder:" -ForegroundColor White
Write-Host "     .\setup_inputs_folder.ps1" -ForegroundColor Cyan
Write-Host ""
Write-Host "  2. Enable 'Run on Startup' for extension in Fusion 360:" -ForegroundColor White
Write-Host "     Utilities -> ADD-INS -> FusionManufacturingPipeline" -ForegroundColor Cyan
Write-Host ""
Write-Host "  3. Start the watcher service:" -ForegroundColor White
Write-Host "     python order_watcher_service.py" -ForegroundColor Cyan
Write-Host ""
Write-Host "  4. Drop JSON files into order_dropbox/ folder" -ForegroundColor White
Write-Host ""
Write-Host "See AUTO_RUN_GUIDE.md for detailed instructions" -ForegroundColor Gray
Write-Host ""
