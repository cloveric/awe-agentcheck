param(
  [string]$SessionFile = '',
  [switch]$All
)

$repo = 'C:/Users/hangw/awe-agentcheck'
$sessionsDir = "$repo/.agents/overnight/sessions"
$lockFile = "$repo/.agents/overnight/overnight.lock"

function Stop-IfRunning([int]$ProcId) {
  if ($ProcId -le 0) {
    return
  }
  try {
    Stop-Process -Id $ProcId -Force -ErrorAction Stop
    Write-Output "[stop] stopped pid=$ProcId"
  } catch {
    Write-Output "[stop] pid=$ProcId not running"
  }
}

if ($All) {
  $nightProcs = Get-CimInstance Win32_Process |
    Where-Object { $_.CommandLine -like '*overnight_autoevolve.py*' -and $_.CommandLine -like '*awe-agentcheck*' } |
    Select-Object -ExpandProperty ProcessId

  foreach ($procId in ($nightProcs | Sort-Object -Unique)) {
    Stop-IfRunning -ProcId $procId
  }

  $sessionFiles = Get-ChildItem -Path $sessionsDir -Filter 'session-*.json' -ErrorAction SilentlyContinue
  foreach ($file in $sessionFiles) {
    try {
      $session = Get-Content -Path $file.FullName -Raw | ConvertFrom-Json
      if ($session.api_started_by_script -eq $true) {
        Stop-IfRunning -ProcId ([int]$session.api_pid)
      }
    } catch {
    }
  }

  if (Test-Path $lockFile) {
    Remove-Item -Path $lockFile -Force -ErrorAction SilentlyContinue
    Write-Output "[stop] removed lock file: $lockFile"
  }
  exit 0
}

if (-not $SessionFile) {
  $latest = Get-ChildItem -Path $sessionsDir -Filter 'session-*.json' -ErrorAction SilentlyContinue | Sort-Object LastWriteTime -Descending | Select-Object -First 1
  if (-not $latest) {
    Write-Output '[stop] no session file found'
    exit 0
  }
  $SessionFile = $latest.FullName
}

if (-not (Test-Path $SessionFile)) {
  Write-Output "[stop] session file not found: $SessionFile"
  exit 1
}

$session = Get-Content -Path $SessionFile -Raw | ConvertFrom-Json

$targets = @($session.overnight_pid)
if ($session.api_started_by_script -eq $true) {
  $targets += @($session.api_pid)
}

foreach ($procId in $targets) {
  if ($procId -and ($procId -as [int])) {
    Stop-IfRunning -ProcId ([int]$procId)
  }
}

if (Test-Path $lockFile) {
  Remove-Item -Path $lockFile -Force -ErrorAction SilentlyContinue
  Write-Output "[stop] removed lock file: $lockFile"
}
