# Instala la skill eda-dengue, el subagente revisor-eda y los permisos en .claude/.
# Correr UNA vez desde la raíz del repo:
#   powershell -ExecutionPolicy Bypass -File .\instalar_claude_setup.ps1
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (-not (Test-Path "_claude_setup")) { throw "No encuentro la carpeta _claude_setup en la raíz del repo." }

New-Item -ItemType Directory -Force ".claude" | Out-Null

foreach ($origen in Get-ChildItem -Path "_claude_setup" -Recurse -File) {
    $relativa = $origen.FullName.Substring((Resolve-Path "_claude_setup").Path.Length + 1)
    $destino = Join-Path ".claude" $relativa
    if ((Test-Path $destino) -and ($relativa -eq "settings.json")) {
        Write-Host "Ya existe .claude\settings.json; no lo sobrescribo. Revisa a mano _claude_setup\settings.json"
        continue
    }
    New-Item -ItemType Directory -Force (Split-Path $destino) | Out-Null
    Copy-Item -Force $origen.FullName $destino
    Write-Host "Instalado $destino"
}

if (Test-Path ".claude\settings.json") { Remove-Item -Recurse -Force "_claude_setup" }
Write-Host "`nListo. Contenido de .claude:"
Get-ChildItem -Recurse -File ".claude" | ForEach-Object { $_.FullName.Substring((Get-Location).Path.Length + 1) }
Remove-Item -Force $PSCommandPath
