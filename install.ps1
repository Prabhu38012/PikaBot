param([switch]$SkipDependencies, [switch]$ElevatedSensor)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root
$python = (Get-Command python.exe -ErrorAction SilentlyContinue).Source
if (-not $python -or $python -like '*WindowsApps*') {
    $python = Join-Path $root '.python\python.exe'
}
if (-not (Test-Path -LiteralPath $python)) {
    throw 'Install Python 3.10+ from python.org first, including pip and tkinter.'
}
if (-not $SkipDependencies) {
    & $python -m pip install -r (Join-Path $root 'requirements.txt')
    if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }
}
$pythonw = Join-Path (Split-Path -Parent $python) 'pythonw.exe'
if (-not (Test-Path -LiteralPath $pythonw)) { throw 'pythonw.exe was not found.' }
$action = New-ScheduledTaskAction -Execute $pythonw -Argument '-m pikabot.main' -WorkingDirectory $root
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$settings = New-ScheduledTaskSettingsSet -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit (New-TimeSpan -Seconds 0) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -MultipleInstances IgnoreNew
$principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive -RunLevel Limited
Register-ScheduledTask -TaskName 'PikabotGuardian' -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Force | Out-Null
$sensor = Join-Path $root 'tools\LibreHardwareMonitor\LibreHardwareMonitor.exe'
if (Test-Path -LiteralPath $sensor) {
    $sensorAction = New-ScheduledTaskAction -Execute $sensor -WorkingDirectory (Split-Path -Parent $sensor)
    $sensorRunLevel = if ($ElevatedSensor) { 'Highest' } else { 'Limited' }
    $sensorPrincipal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive -RunLevel $sensorRunLevel
    Register-ScheduledTask -TaskName 'PikabotSensor' -Action $sensorAction -Trigger $trigger -Settings $settings -Principal $sensorPrincipal -Force | Out-Null
}
Write-Host 'Installed PikabotGuardian. Run it now with: Start-ScheduledTask -TaskName PikabotGuardian'
