param(
    [string]$Python = "python"
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$venvPython = Join-Path $root ".venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $venvPython)) {
    & $Python -m venv (Join-Path $root ".venv")
}

& $venvPython -m pip install --disable-pip-version-check --no-input -r (Join-Path $root "requirements.txt")
Write-Output "Virtual environment ready: $venvPython"
