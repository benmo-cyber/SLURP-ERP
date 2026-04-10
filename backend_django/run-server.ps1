# Run Django with Python 3.12 in a venv stored outside OneDrive (avoids file locks).
$ErrorActionPreference = "Stop"
$BackendRoot = $PSScriptRoot
$VenvRoot = Join-Path $env:LOCALAPPDATA "wwi-erp-backend-venv"
$VenvPython = Join-Path $VenvRoot "Scripts\python.exe"

function Test-Python312 {
    py -3.12 -c "import sys; print(sys.version_info[:2])" 2>$null | Out-Null
    return $LASTEXITCODE -eq 0
}

function Test-PipForPython312 {
    py -3.12 -m pip --version 2>$null | Out-Null
    return $LASTEXITCODE -eq 0
}

if (-not (Test-Python312)) {
    Write-Error "Python 3.12 is not available. Install it (e.g. winget install Python.Python.3.12) and ensure 'py -3.12' works, then re-run this script."
}

if (-not (Test-PipForPython312)) {
    Write-Error @"
Python 3.12 is installed but pip is missing (common with some winget/store builds).

Fix (run in PowerShell outside Cursor if needed):
  1) Download get-pip:  Invoke-WebRequest https://bootstrap.pypa.io/get-pip.py -OutFile `$env:TEMP\get-pip.py
  2) Bootstrap pip:     py -3.12 `$env:TEMP\get-pip.py
  3) Re-run this script: .\run-server.ps1

Or reinstall from https://www.python.org/downloads/release/python-31210/ and enable pip on the installer.
"@
}

if (-not (Test-Path $VenvPython)) {
    Write-Host "Creating venv at $VenvRoot (outside OneDrive)..."
    py -3.12 -m venv $VenvRoot
    if (-not (Test-Path $VenvPython)) {
        Write-Error "Failed to create venv at $VenvRoot"
    }
    if (-not (Test-Path (Join-Path $VenvRoot "Scripts\pip.exe"))) {
        Write-Error @"
Venv was created without pip. Try: py -3.12 -m ensurepip --upgrade
If that fails, bootstrap pip for 3.12 (see message above) then delete the folder $VenvRoot and run this script again.
"@
    }
    & $VenvPython -m pip install --upgrade pip
    & $VenvPython -m pip install -r (Join-Path $BackendRoot "requirements.txt")
}

if (-not (Test-Path (Join-Path $VenvRoot "Scripts\pip.exe"))) {
    Write-Error "Venv at $VenvRoot has no pip. Delete that folder, fix pip for Python 3.12 (see PYTHON_RUNTIME.md), then run this script again."
}

# If venv exists but deps were never installed (or install was interrupted), install now.
& $VenvPython -c "import django" 2>$null | Out-Null
if ($LASTEXITCODE -ne 0) {
    Write-Host "Installing / repairing backend dependencies into venv..."
    & $VenvPython -m pip install --upgrade pip
    & $VenvPython -m pip install -r (Join-Path $BackendRoot "requirements.txt")
}

Set-Location $BackendRoot

# Optional: load backend_django/.env into this process (gitignored) so MAPBOX_ACCESS_TOKEN etc. apply.
$dotenv = Join-Path $BackendRoot ".env"
if (Test-Path $dotenv) {
    Get-Content $dotenv | ForEach-Object {
        $line = $_.Trim()
        if ($line -eq "" -or $line.StartsWith("#")) { return }
        $eq = $line.IndexOf("=")
        if ($eq -lt 1) { return }
        $k = $line.Substring(0, $eq).Trim()
        $v = $line.Substring($eq + 1).Trim()
        if ($v.Length -ge 2 -and (($v.StartsWith('"') -and $v.EndsWith('"')) -or ($v.StartsWith("'") -and $v.EndsWith("'")))) {
            $v = $v.Substring(1, $v.Length - 2)
        }
        Set-Item -Path "env:$k" -Value $v
    }
}

& $VenvPython manage.py runserver @args
