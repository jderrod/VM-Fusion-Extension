# Find Fusion 360 Installation Path

Write-Host "Searching for Fusion 360..." -ForegroundColor Yellow
Write-Host ""

$commonPaths = @(
    "C:\Program Files\Autodesk\Fusion 360\Fusion360.exe",
    "C:\Program Files (x86)\Autodesk\Fusion 360\Fusion360.exe",
    "$env:LOCALAPPDATA\Autodesk\webdeploy\production\Fusion360.exe",
    "$env:APPDATA\Autodesk\webdeploy\production\Fusion360.exe"
)

$foundPath = $null

foreach ($path in $commonPaths) {
    if (Test-Path $path) {
        $foundPath = $path
        Write-Host "[OK] Found Fusion 360 at:" -ForegroundColor Green
        Write-Host "     $foundPath" -ForegroundColor Cyan
        break
    }
}

if (-not $foundPath) {
    Write-Host "[!!] Fusion 360 not found in common locations" -ForegroundColor Red
    Write-Host ""
    Write-Host "Please find Fusion360.exe manually:" -ForegroundColor Yellow
    Write-Host "  1. Open Fusion 360" -ForegroundColor White
    Write-Host "  2. Open Task Manager (Ctrl+Shift+Esc)" -ForegroundColor White
    Write-Host "  3. Find 'Fusion 360' process" -ForegroundColor White
    Write-Host "  4. Right-click -> Open file location" -ForegroundColor White
    Write-Host "  5. Copy the full path to Fusion360.exe" -ForegroundColor White
    Write-Host ""
    Write-Host "Then update line 243 in order_watcher_service.py:" -ForegroundColor Yellow
    Write-Host "  fusion_path = r'YOUR_PATH_HERE'" -ForegroundColor Cyan
} else {
    Write-Host ""
    Write-Host "Update order_watcher_service.py line 243 to:" -ForegroundColor Yellow
    Write-Host "  fusion_path = r'$foundPath'" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "Or copy this to clipboard:" -ForegroundColor Gray
    Write-Host "fusion_path = r'$foundPath'" -ForegroundColor White
    
    # Copy to clipboard if available
    try {
        Set-Clipboard -Value "fusion_path = r'$foundPath'"
        Write-Host ""
        Write-Host "[OK] Path copied to clipboard!" -ForegroundColor Green
    } catch {
        # Clipboard not available
    }
}

Write-Host ""
