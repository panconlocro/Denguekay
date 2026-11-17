# Registers the weekly update of the V4 in the Windows Task Scheduler: Mondays and Thursdays at 07:00.
# (The day the MINSA publishes is not known; two runs bound the wait to four days, and the second one does nothing
# if there is no new epidemiological week.) The task runs scripts\weekly_v4.ps1 from this checkout; a run that was
# missed because the computer was off starts when it is available, and one that exceeds 12 hours is stopped.
# Usage: powershell -NoProfile -ExecutionPolicy Bypass -File scripts\register_weekly_v4_task.ps1
# To remove it: Unregister-ScheduledTask -TaskName "Denguekay actualizacion semanal V4" -Confirm:$false
$ErrorActionPreference = "Stop"

$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$script = Join-Path $root "scripts\weekly_v4.ps1"
$name = "Denguekay actualizacion semanal V4"

$action = New-ScheduledTaskAction -Execute "powershell.exe" -WorkingDirectory $root `
    -Argument ("-NoProfile -ExecutionPolicy Bypass -File `"{0}`"" -f $script)
$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday, Thursday -At "07:00"
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Hours 12)

Register-ScheduledTask -TaskName $name -Action $action -Trigger $trigger -Settings $settings -Force `
    -Description "Actualizacion semanal de Denguekay con la V4 congelada (python -m denguekay.pipelines.v4_weekly)" | Out-Null
Write-Host ("Tarea registrada: {0} (lunes y jueves 07:00). Prueba: Start-ScheduledTask -TaskName '{0}'" -f $name)
