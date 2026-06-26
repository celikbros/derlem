$ErrorActionPreference = "Stop"

function Invoke-Native {
    param(
        [Parameter(Mandatory = $true)][string]$FilePath,
        [Parameter(ValueFromRemainingArguments = $true)][string[]]$Arguments
    )

    & $FilePath @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "$FilePath failed with exit code $LASTEXITCODE"
    }
}

$RootDir = Resolve-Path (Join-Path $PSScriptRoot "..\..")
Set-Location $RootDir

New-Item -ItemType Directory -Force -Path "bin" | Out-Null

Invoke-Native "go" "build" "-trimpath" "-ldflags=-s -w" "-o" "bin\derlem-api.exe" ".\cmd\api"
Invoke-Native "go" "build" "-trimpath" "-ldflags=-s -w" "-o" "bin\derlem-migrate.exe" ".\cmd\migrate"

if (-not (Test-Path ".venv")) {
    Invoke-Native "python" "-m" "venv" ".venv"
}

Invoke-Native ".\.venv\Scripts\python.exe" "-m" "pip" "install" "--upgrade" "pip"
Invoke-Native ".\.venv\Scripts\python.exe" "-m" "pip" "install" "-e" ".\worker"

Push-Location "web"
try {
    Invoke-Native "npm.cmd" "ci"
    Invoke-Native "npm.cmd" "run" "build"
} finally {
    Pop-Location
}
