# Package the Fusion add-in for deployment to the VM.
# Creates a ready-to-copy folder at .\FusionManufacturingPipeline\
# that can be dropped directly into the VM's AddIns directory.
#
# Usage:  Right-click → Run with PowerShell
#         OR:  powershell -ExecutionPolicy Bypass -File package_for_vm.ps1
#         Add -NoPause when calling from another script or a build step.

param([switch]$NoPause)

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
$autostartJson = @'
{
  "_comment": "VM production copy. enabled=true auto-starts folder monitoring on every Fusion launch with no dialogs. The repo/dev copy ships enabled=false, run_mode=LOCAL.",
  "enabled": true,
  "run_mode": "VM",
  "skip_cam": false,
  "skip_drawing": false
}
'@

# Write BOM-less UTF-8. Set-Content -Encoding utf8 on Windows PowerShell 5.1
# emits a BOM, which json.load() rejects outright -- that silently returned {}
# from _read_autostart_config(), so enabled=true never took effect and the VM
# never auto-started. The readers now also tolerate a BOM, but don't add one.
[System.IO.File]::WriteAllText("$PKG\autostart_config.json", $autostartJson,
    (New-Object System.Text.UTF8Encoding($false)))

# Out-of-process file sync service + its Scheduled Task installer.
# These ship inside the package so the service sits next to src/config.py on
# the VM and reads the exact same path mapping the add-in uses.
Copy-Item "$SRC\file_sync_service.py"                  $PKG -Force
Copy-Item "$SRC\setup_sync_task.ps1"                   $PKG -Force

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
Write-Host ""
Write-Host " Then register the file sync service (once per VM):" -ForegroundColor Green
Write-Host "   powershell -ExecutionPolicy Bypass -File setup_sync_task.ps1" -ForegroundColor Yellow
Write-Host ""
Write-Host " Fusion writes only to the local vm_base in local_config.json;" -ForegroundColor Green
Write-Host " the sync service copies from there to the ddc-mefs shares." -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host ""
# Pause so the window stays open when double-clicked. Skipped with -NoPause,
# which is what a build step or another script should use -- otherwise this
# blocks forever waiting for a keypress that never comes.
if (-not $NoPause) {
    try {
        Write-Host "Press any key to exit..."
        $null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
    } catch {
        # No console attached; nothing to wait for.
    }
}
