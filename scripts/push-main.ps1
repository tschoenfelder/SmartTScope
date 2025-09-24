# scripts/push-main.ps1 v5 — minimal & robust
[CmdletBinding()]
param(
  [string]$RepoPath = (Get-Location).Path,
  [string]$KeyPath  = "$env:USERPROFILE\.ssh\id_ed25519",
  [string]$CommitMessage,
  [switch]$MergeCurrentToMain
)

$ErrorActionPreference = 'Stop'

function Resolve-RepoRoot([string]$startDir) {
  $d = (Resolve-Path -LiteralPath $startDir).Path
  while ($true) {
    if (Test-Path -LiteralPath (Join-Path -Path $d -ChildPath ".git")) { return $d }
    $parent = Split-Path -Path $d -Parent
    if ([string]::IsNullOrEmpty($parent) -or $parent -eq $d) { break }
    $d = $parent
  }
  return $null
}

function Ensure-SshAgent {
  $svc = Get-Service -Name 'ssh-agent' -ErrorAction SilentlyContinue
  if (-not $svc) { throw "OpenSSH-Agent nicht installiert. Aktiviere 'OpenSSH Client' in den Windows-Features." }
  if ($svc.Status -ne 'Running') {
    if ($svc.StartType -eq 'Disabled') { Set-Service ssh-agent -StartupType Manual }
    Start-Service ssh-agent
  }
}

function Ensure-KeyLoaded([string]$KeyPath) {
  if (-not (Test-Path $KeyPath)) { throw "Key nicht gefunden: $KeyPath" }
  $sshAdd = "$env:WINDIR\System32\OpenSSH\ssh-add.exe"
  $ids = & $sshAdd -l 2>$null
  if ($LASTEXITCODE -ne 0 -or ($ids -match 'no identities')) {
    Write-Host "ssh-agent: lade Key (24h)..." -ForegroundColor Cyan
    & $sshAdd -t 86400 $KeyPath | Out-Null
    return
  }
  $pub = (Get-Content ($KeyPath + ".pub") -ErrorAction SilentlyContinue) -join ''
  if ($pub) {
    $loaded = & $sshAdd -L 2>$null
    if (-not ($loaded -match ([regex]::Escape(($pub -split '\s+')[1])))) {
      Write-Host "ssh-agent: füge gewünschten Key hinzu (24h)..." -ForegroundColor Cyan
      & $sshAdd -t 86400 $KeyPath | Out-Null
    }
  }
}
# --- Start ---
$repo = Resolve-RepoRoot $RepoPath
if (-not $repo) { throw "Hier ist kein Git-Repository. (Startordner: $RepoPath)" }
Set-Location $repo
Write-Host ("Repo: " + $repo) -ForegroundColor DarkCyan

# echte git.exe ermitteln (wichtig bei OneDrive/PS-Funktionen)
$GitExe = (Get-Command git -CommandType Application -ErrorAction Stop).Source

Ensure-SshAgent
Ensure-KeyLoaded -KeyPath $KeyPath

# erzwinge Windows-OpenSSH für Git
$env:GIT_SSH_COMMAND = "$env:WINDIR\System32\OpenSSH\ssh.exe"

# optional committen, wenn es Änderungen gibt
$status = & $GitExe status --porcelain=v1
if ($CommitMessage -and $status) {
  Write-Host "Committe lokale Änderungen..." -ForegroundColor Yellow
  & $GitExe add -A
  & $GitExe commit -m $CommitMessage
}

# latest holen
& $GitExe fetch origin

# optional: aktuellen Branch -> main mergen
$current = (& $GitExe rev-parse --abbrev-ref HEAD).Trim()
if ($current -ne 'main' -and $MergeCurrentToMain) {
  Write-Host "Merge $current -> main..." -ForegroundColor Yellow
  & $GitExe switch main
  & $GitExe pull --ff-only origin main
  & $GitExe merge --no-ff $current
}

# auf main wechseln, falls nicht dort
$branch = (& $GitExe rev-parse --abbrev-ref HEAD).Trim()
if ($branch -ne 'main') {
  Write-Host "Wechsle auf main zum Push..." -ForegroundColor Yellow
  & $GitExe switch main
}

# Hinweis, falls origin kein SSH ist
$remote = (& $GitExe remote get-url origin)
if ($remote -notmatch '^git@github\.com:') {
  Write-Host "Hinweis: origin nutzt nicht SSH. Empfohlen:" -ForegroundColor Yellow
  Write-Host "git remote set-url origin git@github.com:<user>/SmartTScope.git"
}

# push
& $GitExe push -u origin main
if ($LASTEXITCODE -ne 0) { throw "git push failed ($LASTEXITCODE)" }

Write-Host "✅ Push nach origin/main fertig." -ForegroundColor Green
