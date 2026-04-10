# Start Django API + Vite frontend in separate PowerShell windows (SLURP / WWI ERP).
# Backend uses backend_django\run-server.ps1 (Python 3.12 venv outside OneDrive).
$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
$Backend = Join-Path $Root 'backend_django'
$Frontend = Join-Path $Root 'frontend'

if (-not (Test-Path (Join-Path $Backend 'run-server.ps1'))) {
    Write-Error "Could not find backend_django\run-server.ps1 (expected at: $Backend)"
}
if (-not (Test-Path (Join-Path $Frontend 'package.json'))) {
    Write-Error "Could not find frontend\package.json (expected at: $Frontend)"
}

Write-Host 'Opening Django in a new window (run-server.ps1)...'
Start-Process powershell -ArgumentList @(
    '-NoExit',
    '-Command',
    "Set-Location -LiteralPath '$Backend'; .\run-server.ps1"
)

Write-Host 'Opening Vite dev server in a new window...'
Start-Process powershell -ArgumentList @(
    '-NoExit',
    '-Command',
    "Set-Location -LiteralPath '$Frontend'; npm run dev"
)

Write-Host ''
Write-Host 'Started two windows. Typical URLs:'
Write-Host '  API:      http://127.0.0.1:8000/'
Write-Host '  Frontend: http://localhost:5173/  (port may differ — see Vite output)'
Write-Host ''
