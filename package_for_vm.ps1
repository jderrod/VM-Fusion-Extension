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

# Runtime config. These were previously missed, so each repackage silently
# dropped the VM's autostart settings and the model/drawing mapping.
Copy-Item "$SRC\drawing_config.json"                   $PKG -Force
Copy-Item "$SRC\local_config.json"                     $PKG -Force

# autostart_config.json: the repo copy is the DEV one (enabled=false,
# run_mode=LOCAL). The VM package must auto-start in VM mode, so write the
# production variant rather than copying the dev file verbatim.
@'
{
  "_comment": "VM production copy. enabled=true auto-starts folder monitoring on every Fusion launch with no dialogs. The repo/dev copy ships enabled=false, run_mode=LOCAL.",
  "enabled": true,
  "run_mode": "VM",
  "skip_cam": false,
  "skip_drawing": false
}
'@ | Set-Content -Path "$PKG\autostart_config.json" -Encoding utf8

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
