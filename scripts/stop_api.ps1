param(
  [int]$Port = 8000
)

$ErrorActionPreference = 'Continue'

$repo = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$pidFile = Join-Path $repo '.agents/runtime/api.pid'

function Stop-ByPid([int]$PidToStop) {
  if ($PidToStop -le 0) {
    return
  }
  $proc = Get-Process -Id $PidToStop -ErrorAction SilentlyContinue
  if ($null -eq $proc) {
    Write-Output "[api] pid=$PidToStop not running"
    return
  }
  try {
    Stop-Process -Id $PidToStop -Force -ErrorAction Stop
    Write-Output "[api] stopped pid=$PidToStop"
  } catch {
    Write-Output "[api] failed to stop pid=$PidToStop"
  }
}

if (Test-Path $pidFile) {
  try {
    $raw = (Get-Content -Path $pidFile -TotalCount 1 -ErrorAction Stop | Out-String).Trim()
    $parsed = 0
    if ([int]::TryParse($raw, [ref]$parsed)) {
      Stop-ByPid -PidToStop $parsed
    }
  } catch {
  }
  Remove-Item -Path $pidFile -ErrorAction SilentlyContinue
}

$listeners = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
if ($listeners) {
  $listeners | Select-Object -ExpandProperty OwningProcess -Unique | ForEach-Object {
    Stop-ByPid -PidToStop $_
  }
} else {
  Write-Output "[api] no listener on port $Port"
}
