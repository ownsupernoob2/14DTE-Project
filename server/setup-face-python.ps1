<#
.SYNOPSIS
    Create server\.venv with the Python packages face scanning needs.

    The Go server runs train.py to turn face-scan photos into encodings. When the
    server runs as a scheduled task (SYSTEM), "python" is usually not on its PATH,
    so it looks for this .venv first. Safe to re-run: it only reinstalls when
    requirements.txt has changed.

    Usage (from the server folder):  powershell -ExecutionPolicy Bypass -File setup-face-python.ps1
#>
param([switch]$Force)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$venvPython = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
$stamp      = Join-Path $PSScriptRoot ".venv\.requirements.sha256"
$wanted     = (Get-FileHash -Algorithm SHA256 (Join-Path $PSScriptRoot "requirements.txt")).Hash

if (-not $Force -and (Test-Path $venvPython) -and (Test-Path $stamp) -and ((Get-Content $stamp -Raw).Trim() -eq $wanted)) {
    Write-Host "Face scanning Python is up to date."
    exit 0
}

# Find Python 3.10-3.12 (prebuilt dlib wheels exist for these).
function Find-BasePython {
    $py = Get-Command py.exe -ErrorAction SilentlyContinue
    if ($py) {
        foreach ($v in "3.12", "3.11", "3.10") {
            & $py.Source "-$v" -c "import sys" 2>$null
            if ($LASTEXITCODE -eq 0) { return @($py.Source, "-$v") }
        }
    }
    $candidates = @()
    foreach ($root in @($env:ProgramFiles, $env:LOCALAPPDATA, "C:\")) {
        if ($root) {
            $candidates += Get-ChildItem -Path (Join-Path $root "Python31[012]\python.exe") -ErrorAction SilentlyContinue
            $candidates += Get-ChildItem -Path (Join-Path $root "Programs\Python\Python31[012]\python.exe") -ErrorAction SilentlyContinue
        }
    }
    $candidates += Get-ChildItem -Path "C:\Users\*\AppData\Local\Programs\Python\Python31[012]\python.exe" -ErrorAction SilentlyContinue
    $best = $candidates | Sort-Object FullName -Descending | Select-Object -First 1
    if ($best) { return @($best.FullName) }
    return $null
}

if (-not (Test-Path $venvPython)) {
    $base = Find-BasePython
    if (-not $base) {
        Write-Error "No Python 3.10, 3.11 or 3.12 found. Install one from python.org (tick 'Install for all users'), then run this again."
        exit 1
    }
    Write-Host "Creating .venv with $($base -join ' ')..."
    $base = @($base)
    $exe  = $base[0]
    $rest = @($base | Select-Object -Skip 1)
    & $exe @rest -m venv (Join-Path $PSScriptRoot ".venv")
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path $venvPython)) { Write-Error "Could not create .venv"; exit 1 }
}

Write-Host "Installing face scanning packages..."
& $venvPython -m pip install --quiet --upgrade pip wheel
& $venvPython -m pip install --quiet -r requirements.txt
if ($LASTEXITCODE -ne 0) { Write-Error "pip install failed"; exit 1 }
# face_recognition pins a dlib that must be compiled; dlib-bin (in requirements.txt) is prebuilt.
& $venvPython -m pip install --quiet --no-deps face_recognition
& $venvPython -c "import face_recognition, numpy; print('face_recognition OK')"
if ($LASTEXITCODE -ne 0) { Write-Error "face_recognition did not import"; exit 1 }

Set-Content -Path $stamp -Value $wanted -Encoding ascii
Write-Host "Done. The server will use $venvPython for face scans."
