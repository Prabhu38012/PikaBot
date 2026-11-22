$ErrorActionPreference = 'Stop'
Unregister-ScheduledTask -TaskName 'PikabotGuardian' -Confirm:$false
if (Get-ScheduledTask -TaskName 'PikabotSensor' -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName 'PikabotSensor' -Confirm:$false
}
Write-Host 'Removed PikabotGuardian scheduled task. Files and logs remain.'
