param(
  [string]$Until = '',
  [int]$CheckIntervalSeconds = 20,
  [int]$UnhealthyThreshold = 2,
  [bool]$ForceInitialRestart = $true,
  [switch]$DryRun,
  [switch]$NoAutoMerge,
  [switch]$NoSandbox,
  [string]$MergeTargetPath = '',
  [string]$SandboxWorkspacePath = '',
  [string]$WorkspacePath = 'C:/Users/hangw/awe-agentcheck',
  [string]$Author = 'claude#author-A',
  [string[]]$Reviewers = @('codex#review-B','claude#review-C'),
  [string]$FallbackAuthor = 'codex#author-A',
  [string[]]$FallbackReviewers = @('codex#review-B'),
  [ValidateRange(0,3)][int]$EvolutionLevel = 0,
  [ValidateRange(0,1)][int]$SelfLoopMode = 1,
  [int]$MaxRounds = 3,
  [int]$ParticipantTimeoutSeconds = 3600,
  [int]$CommandTimeoutSeconds = 300,
  [int]$TaskTimeoutSeconds = 1800,
  [int]$PrimaryDisableSeconds = 3600,
  [string]$TestCommand = 'py -m pytest -q',
  [string]$LintCommand = 'py -m ruff check .',
  [string]$ApiBase = 'http://127.0.0.1:8000'
)

$repo = 'C:/Users/hangw/awe-agentcheck'
$launcherPath = "$repo/scripts/start_overnight_until_7.ps1"
$overnightDir = "$repo/.agents/overnight"
$sessionsDir = "$overnightDir/sessions"
New-Item -ItemType Directory -Path $sessionsDir -Force | Out-Null

function Resolve-TargetTime([string]$UntilValue) {
  $now = Get-Date
  if ([string]::IsNullOrWhiteSpace($UntilValue)) {
    throw "Missing required -Until value. Example: -Until '2026-02-18 07:00'."
  }
  try {
    $target = Get-Date $UntilValue
  } catch {
    throw "Invalid -Until value: $UntilValue. Expected parseable datetime like '2026-02-13 06:00'."
  }
  if ($target -le $now) {
    throw "Until must be in the future. Received: $UntilValue"
  }
  return $target
}

function Test-PidAlive([int]$ProcId) {
  if ($ProcId -le 0) {
    return $false
  }
  $proc = Get-Process -Id $ProcId -ErrorAction SilentlyContinue
  return $null -ne $proc
}

$targetTime = Resolve-TargetTime $Until
$untilText = $targetTime.ToString('yyyy-MM-dd HH:mm')
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$logPath = "$overnightDir/supervisor-$stamp.log"
$statePath = "$sessionsDir/supervisor-$stamp.json"

function Write-Log([string]$Message) {
  $line = "[supervisor] $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') $Message"
  Add-Content -Path $logPath -Value $line -Encoding utf8
  Write-Output $line
}

function Test-ApiHealthy([string]$BaseUrl) {
  try {
    $resp = Invoke-WebRequest -UseBasicParsing -Uri "$BaseUrl/healthz" -TimeoutSec 5
    return ($resp.StatusCode -eq 200)
  } catch {
    return $false
  }
}

function Get-ListenerPid([int]$Port) {
  $listener = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
  if ($listener) {
    return [int]$listener.OwningProcess
  }
  return 0
}

function Get-LatestSession() {
  $path = Get-ChildItem -Path $sessionsDir -Filter 'session-*.json' -ErrorAction SilentlyContinue |
    Sort-Object LastWriteTime -Descending |
    Select-Object -First 1
  if (-not $path) {
    return $null
  }
  try {
    return Get-Content -Path $path.FullName -Raw | ConvertFrom-Json
  } catch {
    return $null
  }
}

function Invoke-Launcher([bool]$Force, [bool]$RestartApiNow) {
  $args = @{
    Until = $untilText
    ApiBase = $ApiBase
    WorkspacePath = $WorkspacePath
    Author = $Author
    Reviewers = $Reviewers
    FallbackAuthor = $FallbackAuthor
    FallbackReviewers = $FallbackReviewers
    EvolutionLevel = $EvolutionLevel
    SelfLoopMode = $SelfLoopMode
    MaxRounds = $MaxRounds
    ParticipantTimeoutSeconds = $ParticipantTimeoutSeconds
    CommandTimeoutSeconds = $CommandTimeoutSeconds
    TaskTimeoutSeconds = $TaskTimeoutSeconds
    PrimaryDisableSeconds = $PrimaryDisableSeconds
    TestCommand = $TestCommand
    LintCommand = $LintCommand
  }
  if ($DryRun) {
    $args.DryRun = $true
  }
  if ($NoAutoMerge) {
    $args.NoAutoMerge = $true
  }
  if ($NoSandbox) {
    $args.NoSandbox = $true
  }
  if (-not [string]::IsNullOrWhiteSpace($MergeTargetPath)) {
    $args.MergeTargetPath = $MergeTargetPath
  }
  if (-not [string]::IsNullOrWhiteSpace($SandboxWorkspacePath)) {
    $args.SandboxWorkspacePath = $SandboxWorkspacePath
  }
  if ($Force) {
    $args.ForceRestart = $true
  }
  if ($RestartApiNow) {
    $args.RestartApi = $true
  }
  Write-Log "launcher start force=$Force restart_api=$RestartApiNow until=$untilText"
  & $launcherPath @args 2>&1 | ForEach-Object { Write-Log "$_" }
}

$apiUri = [Uri]$ApiBase
$apiPort = [int]$apiUri.Port
$initialState = [ordered]@{
  started_at = (Get-Date).ToString('s')
  until = $untilText
  evolution_level = $EvolutionLevel
  api_base = $ApiBase
  check_interval_seconds = $CheckIntervalSeconds
  unhealthy_threshold = $UnhealthyThreshold
  force_initial_restart = $ForceInitialRestart
  log_path = $logPath
}
$initialState | ConvertTo-Json -Depth 4 | Set-Content -Path $statePath -Encoding utf8

Write-Log "supervisor started until=$untilText api=$ApiBase state_file=$statePath"
Invoke-Launcher -Force:$ForceInitialRestart -RestartApiNow:$ForceInitialRestart

$unhealthyStreak = 0
while ((Get-Date) -lt $targetTime) {
  $session = Get-LatestSession
  $nightPid = if ($session -and $session.overnight_pid) { [int]$session.overnight_pid } else { 0 }
  $nightAlive = Test-PidAlive $nightPid
  $listenerPid = Get-ListenerPid $apiPort
  $apiHealthy = ($listenerPid -gt 0) -and (Test-ApiHealthy $ApiBase)

  if ($nightAlive -and $apiHealthy) {
    if ($unhealthyStreak -ne 0) {
      Write-Log "health restored listener_pid=$listenerPid overnight_pid=$nightPid"
    }
    $unhealthyStreak = 0
  } else {
    $unhealthyStreak += 1
    Write-Log "health check failed streak=$unhealthyStreak listener_pid=$listenerPid overnight_alive=$nightAlive"
    if ($unhealthyStreak -ge [Math]::Max(1, $UnhealthyThreshold)) {
      Write-Log 'threshold exceeded, restarting orchestrator stack'
      Invoke-Launcher -Force:$true -RestartApiNow:$true
      $unhealthyStreak = 0
    }
  }

  Start-Sleep -Seconds ([Math]::Max(5, $CheckIntervalSeconds))
}

Write-Log "deadline reached ($untilText), supervisor exiting"
