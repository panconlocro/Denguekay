# Weekly update of the Denguekay service with the frozen V4 (python -m denguekay.pipelines.v4_weekly).
# It appends stdout and stderr to models\serving\actualizacion_semanal\logs\<yyyyMMdd>.log and exits with the code of
# the module (0: emitted, without news, loaded without emitting or dry run; 1: failed).
# Usage, from any folder:
#   powershell -NoProfile -ExecutionPolicy Bypass -File scripts\weekly_v4.ps1 [--inicial] [--dry-run]
#       [--sin-descargas] [--forzar] [--reemitir]
# scripts\register_weekly_v4_task.ps1 schedules it with the Windows Task Scheduler.
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")

$python = Join-Path (Get-Location) ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    Write-Error "No existe .venv\Scripts\python.exe; ejecute scripts\setup.ps1"
    exit 1
}

$logs = Join-Path (Get-Location) "models\serving\actualizacion_semanal\logs"
New-Item -ItemType Directory -Force $logs | Out-Null
$log = Join-Path $logs ("{0:yyyyMMdd}.log" -f (Get-Date))
$out = [System.IO.Path]::GetTempFileName()
$err = [System.IO.Path]::GetTempFileName()
$env:PYTHONIOENCODING = "utf-8"

Add-Content -Path $log -Encoding UTF8 -Value ("=== {0:yyyy-MM-dd HH:mm:ss} v4_weekly {1}" -f (Get-Date), ($args -join " "))
try {
    $process = Start-Process -FilePath $python -ArgumentList (@("-m", "denguekay.pipelines.v4_weekly") + $args) `
        -NoNewWindow -Wait -PassThru -RedirectStandardOutput $out -RedirectStandardError $err
    foreach ($file in @($out, $err)) {
        $text = [System.IO.File]::ReadAllText($file, [System.Text.Encoding]::UTF8)
        if ($text.Length -gt 0) { Add-Content -Path $log -Encoding UTF8 -Value $text }
    }
    Add-Content -Path $log -Encoding UTF8 -Value ("=== exit {0}" -f $process.ExitCode)
    exit $process.ExitCode
}
finally {
    Remove-Item $out, $err -ErrorAction SilentlyContinue
}
