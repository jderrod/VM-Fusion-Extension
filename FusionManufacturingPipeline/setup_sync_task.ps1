# Register file_sync_service.py as a Windows Scheduled Task on the VM.
#
# The service copies the pipeline's local output folders to the network
# shares out-of-process, so Fusion never blocks on a network write.
#
# Usage (run on the VM, from the installed add-in folder):
#     powershell -ExecutionPolicy Bypass -File setup_sync_task.ps1
#     powershell -ExecutionPolicy Bypass -File setup_sync_task.ps1 -Remove
#
# The task is registered to run AT LOGON of the current user, in that user's
# security context. This is deliberate and matters: a task running as SYSTEM
# has no credentials for the \\ddc-mefs shares and every copy would fail with
# access denied. The VM auto-logs-in to run Fusion, so logon is equivalent to
# boot here, and it needs no stored password.

param(
    [switch]$Remove,
    [string]$PythonExe = "",
    [int]$Interval = 15
)

$ErrorActionPreference = "Stop"
$TaskName = "FusionPipelineFileSync"
$Root     = $PSScriptRoot
$Script   = Join-Path $Root "file_sync_service.py"

if ($Remove) {
    if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
        Write-Host "Removed scheduled task '$TaskName'." -ForegroundColor Green
    } else {
        Write-Host "No scheduled task named '$TaskName' found." -ForegroundColor Yellow
    }
    return
}

if (-not (Test-Path $Script)) {
    throw "Cannot find file_sync_service.py next to this script (looked in $Root)."
}

# Locate a Python interpreter. pythonw.exe is preferred so the service runs
# without a console window on the VM desktop.
if ($PythonExe -eq "") {
    $candidates = @()
    $pyw = Get-Command pythonw.exe -ErrorAction SilentlyContinue
    if ($pyw) { $candidates += $pyw.Source }
    $py = Get-Command python.exe -ErrorAction SilentlyContinue
    if ($py) { $candidates += $py.Source }
    $candidates += @(
        "$env:LOCALAPPDATA\Programs\Python\Python312\pythonw.exe",
        "$env:LOCALAPPDATA\Programs\Python\Python311\pythonw.exe",
        "$env:LOCALAPPDATA\Programs\Python\Python310\pythonw.exe"
    )
    $PythonExe = $candidates | Where-Object { $_ -and (Test-Path $_) } | Select-Object -First 1
}

if (-not $PythonExe -or -not (Test-Path $PythonExe)) {
    throw "Could not find a Python interpreter. Pass one explicitly: -PythonExe 'C:\Path\to\pythonw.exe'"
}

Write-Host "Python:  $PythonExe"
Write-Host "Service: $Script"

$action = New-ScheduledTaskAction -Execute $PythonExe `
    -Argument "`"$Script`" --interval $Interval" `
    -WorkingDirectory $Root

$trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME

# Run in the interactive user's context so UNC share access is authenticated.
$principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" `
    -LogonType Interactive -RunLevel Limited

# The service is meant to stay up for the life of the session: no execution
# time limit, restart if it ever dies, and start late if the trigger is missed.
$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -RestartCount 999 `
    -RestartInterval (New-TimeSpan -Minutes 1) `
    -ExecutionTimeLimit (New-TimeSpan -Seconds 0)

if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
    Write-Host "Replaced existing task." -ForegroundColor Yellow
}

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger `
    -Principal $principal -Settings $settings `
    -Description "Mirrors the Fusion pipeline's local output folders to the ddc-mefs network shares, out-of-process so Fusion never blocks on a network write." | Out-Null

Write-Host ""
Write-Host "========================================" -ForegroundColor Green
Write-Host " Registered scheduled task '$TaskName'" -ForegroundColor Green
Write-Host "   Trigger: at logon of $env:USERNAME" -ForegroundColor Yellow
Write-Host "   Poll:    every $Interval seconds" -ForegroundColor Yellow
Write-Host ""
Write-Host " Start it now without logging out:" -ForegroundColor Green
Write-Host "   Start-ScheduledTask -TaskName $TaskName" -ForegroundColor Yellow
Write-Host ""
Write-Host " Check it is running:" -ForegroundColor Green
Write-Host "   Get-ScheduledTask -TaskName $TaskName | Get-ScheduledTaskInfo" -ForegroundColor Yellow
Write-Host "========================================" -ForegroundColor Green
