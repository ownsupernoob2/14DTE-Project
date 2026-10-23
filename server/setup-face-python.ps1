<#
.SYNOPSIS
    Create server\.venv with the Python packages face scanning needs.

    The Go server runs train.py to turn face-scan photos into encodings. When the
    server runs as a scheduled task (SYSTEM), "python" is usually not on its PATH,
    so it looks for this .venv first. Safe to re-run: it only reinstalls when
    requirements.txt has changed or face_recognition no longer imports.

    No Python 3.10-3.12 on the machine? It downloads python.org's own Python
    3.12 package (from NuGet, no installer, no admin rights) into server\.python
    and builds the .venv from that. The auto-updater runs this script after each
    update, so this needs no one at the server.

    Usage (from the server folder):  powershell -ExecutionPolicy Bypass -File setup-face-python.ps1
#>
param([switch]$Force)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$venvDir    = Join-Path $PSScriptRoot ".venv"
$venvPython = Join-Path $venvDir "Scripts\python.exe"
$stamp      = Join-Path $venvDir ".requirements.sha256"
$wanted     = (Get-FileHash -Algorithm SHA256 (Join-Path $PSScriptRoot "requirements.txt")).Hash

$privateDir    = Join-Path $PSScriptRoot ".python"
$privatePython = Join-Path $privateDir "tools\python.exe"
$nugetVersion  = "3.12.10"

function Test-FaceImport($python) {
    if (-not (Test-Path $python)) { return $false }
    # Its import warnings go to stderr, which "Stop" would turn into a failure.
    $ErrorActionPreference = "Continue"
    & $python -c "import face_recognition, numpy" 2>$null | Out-Null
    return ($LASTEXITCODE -eq 0)
}

if (-not $Force -and (Test-Path $stamp) -and ((Get-Content $stamp -Raw).Trim() -eq $wanted) -and (Test-FaceImport $venvPython)) {
    Write-Host "Face scanning Python is up to date."
    exit 0
}

# Find Python 3.10-3.12 (prebuilt dlib wheels exist for these).
function Find-BasePython {
    if (Test-Path $privatePython) { return @($privatePython) }      # downloaded earlier
    $ErrorActionPreference = "Continue"
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

# python.org's Python, packaged for NuGet: a plain zip, nothing to install.
function Get-PrivatePython {
    Write-Host "No Python 3.10-3.12 found: downloading Python $nugetVersion into .python ..."
    $zip = Join-Path $env:TEMP "python.$nugetVersion.nupkg.zip"
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    Invoke-WebRequest -UseBasicParsing -OutFile $zip `
        -Uri "https://api.nuget.org/v3-flatcontainer/python/$nugetVersion/python.$nugetVersion.nupkg"
    if (Test-Path $privateDir) { Remove-Item -Recurse -Force $privateDir }
    Expand-Archive -Force $zip $privateDir
    Remove-Item -Force $zip
    if (-not (Test-Path $privatePython)) { Write-Error "Downloaded Python has no tools\python.exe" }
    return @($privatePython)
}

# Native tools (venv, pip) write warnings to stderr. When this script's output
# is captured (the updater and the server both do), Windows PowerShell turns
# those into errors and "Stop" would abort: these steps check exit codes instead.
function New-FaceVenv($base) {
    $ErrorActionPreference = "Continue"
    if (Test-Path $venvDir) { Remove-Item -Recurse -Force $venvDir }
    Write-Host "Creating .venv with $($base -join ' ')..."
    $base = @($base)
    $exe  = $base[0]
    $rest = @($base | Select-Object -Skip 1)
    & $exe @rest -m venv $venvDir 2>&1 | ForEach-Object { "$_" }
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path $venvPython)) { throw "Could not create .venv" }
}

function Install-FacePackages {
    $ErrorActionPreference = "Continue"
    Write-Host "Installing face scanning packages..."
    & $venvPython -m pip install --quiet --disable-pip-version-check --upgrade pip wheel 2>&1 | ForEach-Object { "$_" }
    & $venvPython -m pip install --quiet --disable-pip-version-check -r requirements.txt 2>&1 | ForEach-Object { "$_" }
    if ($LASTEXITCODE -ne 0) { throw "pip install failed" }
    # face_recognition pins a dlib that must be compiled; dlib-bin (in requirements.txt) is prebuilt.
    & $venvPython -m pip install --quiet --disable-pip-version-check --no-deps face_recognition 2>&1 | ForEach-Object { "$_" }
    if ($LASTEXITCODE -ne 0) { throw "pip install face_recognition failed" }
}

# 1. Build (or repair) the .venv from whatever Python this machine has.
$base = Find-BasePython
if (-not $base) { $base = Get-PrivatePython }
if (-not (Test-Path $venvPython) -or -not (Test-FaceImport $venvPython)) {
    New-FaceVenv $base
}
Install-FacePackages

# 2. Still no good (a broken or unsuitable system Python)? Start again from
#    the downloaded one, which is known to work.
if (-not (Test-FaceImport $venvPython) -and ($base[0] -ne $privatePython)) {
    Write-Host "face_recognition did not import with $($base -join ' '); retrying with a private Python."
    $base = Get-PrivatePython
    New-FaceVenv $base
    Install-FacePackages
}

if (-not (Test-FaceImport $venvPython)) { Write-Error "face_recognition did not import" }
Write-Host "face_recognition OK"
Set-Content -Path $stamp -Value $wanted -Encoding ascii
Write-Host "Done. The server will use $venvPython for face scans."
