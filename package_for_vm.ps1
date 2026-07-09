# Package the Fusion add-in for deployment to the VM.
# Creates a ready-to-copy folder at .\FusionManufacturingPipeline\
# that can be dropped directly into the VM's AddIns directory.
#
# Usage:  Right-click → Run with PowerShell
#         OR:  powershell -ExecutionPolicy Bypass -File package_for_vm.ps1

$SRC = $PSScriptRoot
$PKG = Join-Path $SRC "FusionManufacturingPipeline"

# Clean previous package
if (Test-Path $PKG) { Remove-Item $PKG -Recurse -Force }
New-Item -ItemType Directory -Path $PKG | Out-Null

# Root files
Copy-Item "$SRC\FusionManufacturingPipeline.py"       $PKG -Force
Copy-Item "$SRC\FusionManufacturingPipeline.manifest"  $PKG -Force
Copy-Item "$SRC\schema.json"                           $PKG -Force

# src folder (all Python modules)
Copy-Item "$SRC\src" "$PKG\src" -Recurse -Force

# Post processor files
Copy-Item "$SRC\Post Processing" "$PKG\Post Processing" -Recurse -Force

# UI icons
Copy-Item "$SRC\UI Elements" "$PKG\UI Elements" -Recurse -Force

Write-Host ""
Write-Host "========================================" -ForegroundColor Green
Write-Host " Package created at:" -ForegroundColor Green
Write-Host "   $PKG" -ForegroundColor Yellow
Write-Host ""
Write-Host " On the VM, copy this folder to:" -ForegroundColor Green
Write-Host "   %APPDATA%\Autodesk\Autodesk Fusion 360\API\AddIns\FusionManufacturingPipeline" -ForegroundColor Yellow
Write-Host "========================================" -ForegroundColor Green
Write-Host ""
Write-Host "Press any key to exit..."
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
