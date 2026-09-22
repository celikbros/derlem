<#
.SYNOPSIS
  Derlem'in uc servisini TEK terminalden baslatir ve birlikte kapatir.

.DESCRIPTION
  API, worker ve web'i cocuk surec olarak baslatir. Ctrl+C ya da pencerenin
  kapanmasi ucunu birden durdurur. `go run` yerine `go build` kullanilir:
  `go run` terminal kapatilinca derledigi cocuk exe'yi ortada birakiyor.

  Ciktilar var/run altina yazilir:
    api.log - worker.log - web.log

  Canli izlemek icin ayri bir pencerede:
    Get-Content -Wait "var\run\api.log"

.EXAMPLE
  .\scripts\dev-up.ps1
  .\scripts\dev-up.ps1 -NoWeb        # yalniz API + worker
#>
[CmdletBinding()]
param(
  [switch]$NoWeb,
  [switch]$SkipBuild
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$runDir = Join-Path $root 'var\run'
if (-not (Test-Path $runDir)) { New-Item -ItemType Directory -Path $runDir | Out-Null }

$apiExe = Join-Path $runDir 'derlem-api.exe'
$venvPython = Join-Path $root '.venv\Scripts\python.exe'
$children = @()

function Write-Step { param([string]$Message) Write-Host "==> $Message" -ForegroundColor Cyan }
function Write-Ok   { param([string]$Message) Write-Host "    $Message" -ForegroundColor Green }
function Write-Warn { param([string]$Message) Write-Host "    $Message" -ForegroundColor Yellow }

function Stop-Children {
  Write-Host ''
  Write-Step 'Servisler durduruluyor'
  foreach ($child in $children) {
    if ($null -eq $child) { continue }
    try {
      if (-not $child.HasExited) {
        # Once agaci kapat: web (npm) alt surec dogurur
        & taskkill.exe /PID $child.Id /T /F *> $null
        Write-Ok "$($child.ProcessName) (PID $($child.Id)) durduruldu"
      }
    } catch {
      Write-Warn "PID $($child.Id) durdurulamadi: $($_.Exception.Message)"
    }
  }
  Write-Ok 'Hepsi kapandi.'
}

function Start-Child {
  param(
    [Parameter(Mandatory)][string]$Name,
    [Parameter(Mandatory)][string]$FilePath,
    [string[]]$Arguments = @(),
    [string]$WorkingDirectory = $root
  )
  $out = Join-Path $runDir "$Name.log"
  $err = Join-Path $runDir "$Name.err.log"
  if (Test-Path $out) { Remove-Item $out -Force }
  if (Test-Path $err) { Remove-Item $err -Force }
  $splat = @{
    FilePath               = $FilePath
    WorkingDirectory       = $WorkingDirectory
    RedirectStandardOutput = $out
    RedirectStandardError  = $err
    PassThru               = $true
    NoNewWindow            = $true
  }
  if ($Arguments.Count -gt 0) { $splat['ArgumentList'] = $Arguments }
  $process = Start-Process @splat
  Write-Ok "$Name basladi (PID $($process.Id)) -> var\run\$Name.log"
  return $process
}

# --- Onkosullar -------------------------------------------------------------

Write-Step 'Onkosullar'
if (-not (Test-Path (Join-Path $root '.env'))) { throw '.env bulunamadi.' }
if (-not (Test-Path $venvPython)) { throw "Python sanal ortami yok: $venvPython" }

$busy = Get-NetTCPConnection -State Listen -LocalPort 18401 -ErrorAction SilentlyContinue
if ($busy) {
  throw "18401 portu zaten dinleniyor (PID $($busy.OwningProcess)). Eski surec ayakta: .\scripts\dev-down.ps1 ile kapatin."
}
if (-not $NoWeb) {
  $busyWeb = Get-NetTCPConnection -State Listen -LocalPort 18400 -ErrorAction SilentlyContinue
  if ($busyWeb) {
    throw "18400 portu zaten dinleniyor (PID $($busyWeb.OwningProcess)). .\scripts\dev-down.ps1 ile kapatin."
  }
}
Write-Ok 'Portlar bos.'

Import-Module CimCmdlets -ErrorAction SilentlyContinue | Out-Null
$staleWorker = Get-CimInstance Win32_Process |
  Where-Object { $_.CommandLine -and $_.CommandLine -match 'derlem_worker' -and $_.CommandLine -match [regex]::Escape($root) }
if ($staleWorker) {
  $pids = ($staleWorker | ForEach-Object { $_.ProcessId }) -join ', '
  throw "Bu depodan bir worker zaten calisiyor (PID $pids). Once .\scripts\dev-down.ps1 calistirin."
}
Write-Ok 'Ayakta worker yok.'

# --- API'yi derle -----------------------------------------------------------

if (-not $SkipBuild) {
  Write-Step 'API derleniyor (go build)'
  & go build -o $apiExe ./cmd/api
  if ($LASTEXITCODE -ne 0) { throw "go build basarisiz (cikis $LASTEXITCODE)." }
  Write-Ok 'Derlendi.'
} elseif (-not (Test-Path $apiExe)) {
  throw "-SkipBuild verildi ama $apiExe yok."
}

# --- Baslat -----------------------------------------------------------------

try {
  Write-Step 'Servisler baslatiliyor'
  $children += Start-Child -Name 'api' -FilePath $apiExe

  # API ayaga kalksin (en fazla 20 sn)
  $ready = $false
  for ($i = 0; $i -lt 40; $i++) {
    Start-Sleep -Milliseconds 500
    if ($children[0].HasExited) { break }
    try {
      $null = Invoke-WebRequest -Uri 'http://127.0.0.1:18401/api/v1/health' -TimeoutSec 2 -UseBasicParsing
      $ready = $true
      break
    } catch { }
  }
  if ($children[0].HasExited) {
    Write-Warn 'API basladigi gibi kapandi. Hata:'
    Get-Content (Join-Path $runDir 'api.err.log') -Tail 20 -ErrorAction SilentlyContinue
    Get-Content (Join-Path $runDir 'api.log') -Tail 20 -ErrorAction SilentlyContinue
    throw 'API ayaga kalkmadi.'
  }
  if ($ready) { Write-Ok 'API saglikli: http://127.0.0.1:18401' } else { Write-Warn 'API saglik yanit vermedi, yine de devam ediliyor.' }

  $children += Start-Child -Name 'worker' -FilePath $venvPython -Arguments @('-m', 'derlem_worker', '--worker-id', 'local-worker')

  if (-not $NoWeb) {
    $npm = (Get-Command npm.cmd -ErrorAction SilentlyContinue)
    if ($null -eq $npm) { $npm = (Get-Command npm -ErrorAction SilentlyContinue) }
    if ($null -eq $npm) { throw 'npm bulunamadi.' }
    $children += Start-Child -Name 'web' -FilePath $npm.Source -Arguments @('run', 'dev') -WorkingDirectory (Join-Path $root 'web')
  }

  Write-Host ''
  Write-Step 'Hazir'
  Write-Host '    Web:    http://localhost:18400' -ForegroundColor White
  Write-Host '    API:    http://127.0.0.1:18401' -ForegroundColor White
  Write-Host '    Loglar: var\run\{api,worker,web}.log' -ForegroundColor White
  Write-Host ''
  Write-Host '    Kapatmak icin bu pencerede Ctrl+C.' -ForegroundColor Yellow
  Write-Host ''

  # Beklerken: bir cocuk kendiliginden olurse haber ver
  while ($true) {
    Start-Sleep -Seconds 2
    foreach ($child in $children) {
      if ($child.HasExited) {
        Write-Warn "$($child.ProcessName) (PID $($child.Id)) beklenmedik sekilde kapandi (cikis $($child.ExitCode))."
        throw 'Bir servis kapandi; hepsi durduruluyor.'
      }
    }
  }
} finally {
  Stop-Children
}
