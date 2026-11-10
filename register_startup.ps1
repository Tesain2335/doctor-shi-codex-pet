$ErrorActionPreference = 'Stop'
$appDirectory = (Resolve-Path -LiteralPath $env:CODEXPET_APP_DIRECTORY).Path
$taskName = 'CodexPetCompanion'
$existingTask = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
$taskWasActive = $existingTask -and ($existingTask.State -in @('Running', 'Queued'))
if ($existingTask) {
    $backupDirectory = Join-Path $env:LOCALAPPDATA 'CodexPet'
    [System.IO.Directory]::CreateDirectory($backupDirectory) | Out-Null
    $backupName = 'startup-task-before-' + (Get-Date -Format 'yyyyMMdd-HHmmss') + '.xml'
    [System.IO.File]::WriteAllText((Join-Path $backupDirectory $backupName), (Export-ScheduledTask -TaskName $taskName), [System.Text.Encoding]::Unicode)
    if ($taskWasActive) {
        Stop-ScheduledTask -TaskName $taskName -ErrorAction Stop
        for ($attempt = 0; $attempt -lt 50; $attempt++) {
            if ((Get-ScheduledTask -TaskName $taskName).State -notin @('Running','Queued')) { break }
            Start-Sleep -Milliseconds 100
        }
    }
}
$ownedScripts = @('launch.py','companion.py','gui_entry.py') | ForEach-Object { Join-Path $appDirectory $_ }
Get-CimInstance Win32_Process | Where-Object {
    $candidate = $_
    $candidate.Name -in @('python.exe','pythonw.exe') -and @($ownedScripts | Where-Object {
        $candidate.CommandLine -and $candidate.CommandLine.IndexOf($_,[System.StringComparison]::OrdinalIgnoreCase) -ge 0
    }).Count -gt 0
} | ForEach-Object { Stop-Process -Id $_.ProcessId -ErrorAction SilentlyContinue }
$taskUser = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$runtimePath = (Resolve-Path -LiteralPath $env:CODEXPET_BASE_PYTHONW).Path
$launchPath = Join-Path $appDirectory 'launch.py'
$taskAction = New-ScheduledTaskAction -Execute $runtimePath -Argument ('"' + $launchPath + '"') -WorkingDirectory $appDirectory
$taskTrigger = New-ScheduledTaskTrigger -AtLogOn -User $taskUser
$taskTrigger.Delay = 'PT15S'
$taskPrincipal = New-ScheduledTaskPrincipal -UserId $taskUser -LogonType Interactive -RunLevel Limited
$taskSettings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -ExecutionTimeLimit ([TimeSpan]::Zero) -MultipleInstances IgnoreNew -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)
$definition = New-ScheduledTask -Action $taskAction -Trigger $taskTrigger -Principal $taskPrincipal -Settings $taskSettings -Description 'Doctor-shi desktop pet. Visible at user sign-in; local startup logs; no password stored.'
try { Register-ScheduledTask -TaskName $taskName -InputObject $definition -Force | Out-Null }
catch {
    if ($taskWasActive) { Start-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue }
    throw
}
$xml = Export-ScheduledTask -TaskName $taskName
[System.IO.File]::WriteAllText((Join-Path $appDirectory 'startup-task.xml'), $xml, [System.Text.Encoding]::Unicode)
[PSCustomObject]@{ TaskName = $taskName; LogonType = 'Interactive'; Delay = 'PT15S'; RestartCount = 3; ExecutionTimeLimit = 'PT0S' } | ConvertTo-Json -Compress
