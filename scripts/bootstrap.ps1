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

if (Test-Path -LiteralPath (Join-Path $root "package-lock.json")) {
    if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
        throw "Node.js/npm is required to install the Pagefind builder dependency."
    }
    Push-Location $root
    try {
        & npm ci
    } finally {
        Pop-Location
    }
}

Write-Output "Virtual environment ready: $venvPython"
