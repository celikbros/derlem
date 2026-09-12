# Derlem test runner: runs everything, database-backed integration tests included.
# Plain ASCII on purpose -- Windows PowerShell 5.1 reads a BOM-less UTF-8 .ps1 as
# ANSI and would mangle Turkish characters in these messages.
#
# If DERLEM_TEST_DATABASE_URL is missing, database-backed tests FAIL rather than
# skip silently (see internal/testdb, worker/tests/conftest.py). This script
# supplies it from .env, or derives it from DATABASE_URL.
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

if (-not $env:DERLEM_TEST_DATABASE_URL) {
    $envFile = Join-Path $root ".env"
    if (Test-Path $envFile) {
        $lines = Get-Content $envFile
        foreach ($line in $lines) {
            if ($line -match '^\s*DERLEM_TEST_DATABASE_URL\s*=\s*(.+)$') {
                $env:DERLEM_TEST_DATABASE_URL = $Matches[1].Trim()
            }
        }
        if (-not $env:DERLEM_TEST_DATABASE_URL) {
            foreach ($line in $lines) {
                if ($line -match '^\s*DATABASE_URL\s*=\s*(.+)$') {
                    # Swap the working database name for the scratch one; user,
                    # password and host stay as they are.
                    $env:DERLEM_TEST_DATABASE_URL = ($Matches[1].Trim() -replace '/derlem(\?|$)', '/derlem_ci_test$1')
                }
            }
        }
    }
}
if (-not $env:DERLEM_TEST_DATABASE_URL) {
    throw "DERLEM_TEST_DATABASE_URL is not set and could not be derived from .env. See docs/local_development.md > Testler"
}

$dbName = ($env:DERLEM_TEST_DATABASE_URL -replace '.*/([^/?]+).*', '$1')
if ($dbName -notmatch '_test$') {
    throw "Test database name must end in _test; '$dbName' may be the working database. Integration tests create and drop schemas with CASCADE."
}
Write-Host "Test database: $dbName"

Write-Host "== Go =="
go test ./...
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "== Worker =="
& (Join-Path $root ".venv\Scripts\python.exe") -m pytest worker\tests -q -rs
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "All tests green (database-backed tests included)."
