<#
.SYNOPSIS
  Derlem'in ayakta kalmis servislerini bulur ve kapatir.

.DESCRIPTION
  `dev-up.ps1` normalde kendi cocuklarini kapatir. Terminal zorla kapandiysa
  ya da servisler elle baslatildiysa ortada surec kalabilir. Bu betik YALNIZ
  bu depoya ait surecleri oldurur; komut satirinda depo yolunu arar.

  Kapsam: derlem-api.exe - go run ./cmd/api - derlem_worker - web icin next dev

.EXAMPLE
  .\scripts\dev-down.ps1
  .\scripts\dev-down.ps1 -WhatIf     # yalniz listeler, oldurmez
#>
[CmdletBinding(SupportsShouldProcess)]
param()

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$rootPattern = [regex]::Escape($root)

$patterns = @(
  @{ Name = 'API (derlem-api.exe)'; Regex = "$rootPattern.*derlem-api" },
  @{ Name = 'API (go run)';         Regex = "$rootPattern.*cmd[\\/]api" },
  @{ Name = 'Worker';               Regex = 'derlem_worker' },
  @{ Name = 'Web (next dev)';       Regex = "$rootPattern.*(next|npm).*dev|dev.*$rootPattern.*web" }
)

Import-Module CimCmdlets -ErrorAction SilentlyContinue | Out-Null
$all = Get-CimInstance Win32_Process | Where-Object { $_.CommandLine }
$found = @()

foreach ($pattern in $patterns) {
  foreach ($process in $all) {
    if ($process.CommandLine -match $pattern.Regex) {
      # Baska bir depoda ayni isimli surec varsa dokunmayalim: komut satiri ya da
      # calisma dizini bu depoyu gostermeli.
      if ($process.CommandLine -notmatch $rootPattern -and $pattern.Name -eq 'Worker') {
        $parentPath = try { (Get-Process -Id $process.ProcessId).Path } catch { $null }
        if ($parentPath -and $parentPath -notlike "$root*") { continue }
      }
      $found += [pscustomobject]@{
        Rol  = $pattern.Name
        PID  = $process.ProcessId
        Komut = $process.CommandLine.Substring(0, [Math]::Min(110, $process.CommandLine.Length))
      }
    }
  }
}

$found = $found | Sort-Object PID -Unique
if ($found.Count -eq 0) {
  Write-Host 'Ayakta Derlem sureci bulunamadi.' -ForegroundColor Green
  return
}

$found | Format-Table -AutoSize | Out-String | Write-Host

foreach ($item in $found) {
  if ($PSCmdlet.ShouldProcess("PID $($item.PID) - $($item.Rol)", 'Kapat')) {
    try {
      & taskkill.exe /PID $item.PID /T /F *> $null
      Write-Host "  kapatildi: PID $($item.PID) ($($item.Rol))" -ForegroundColor Green
    } catch {
      Write-Host "  kapatilamadi: PID $($item.PID) - $($_.Exception.Message)" -ForegroundColor Yellow
    }
  }
}

foreach ($port in 18400, 18401) {
  $listen = Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue
  if ($listen) {
    Write-Host "  UYARI: $port hala dinleniyor (PID $($listen.OwningProcess))." -ForegroundColor Yellow
  } else {
    Write-Host "  $port bos." -ForegroundColor Green
  }
}
