# scripts/push-main-https.ps1
[CmdletBinding()]
param([string]$CommitMessage, [switch]$MergeCurrentToMain)

$ErrorActionPreference = 'Stop'

function RepoRoot([string]$startDir) {
  $d = (Resolve-Path -LiteralPath $startDir).Path
  while ($true) {
    if (Test-Path (Join-Path $d ".git")) { return $d }
    $p = Split-Path $d -Parent
    if ($p -eq $d) { break }; $d = $p
  }
  throw "Kein Git-Repo gefunden."
}

function Run([string]$cmd) {
  Write-Host "→ $cmd"
  & cmd.exe /c $cmd
  if ($LASTEXITCODE -ne 0) { throw "Fehler bei: $cmd" }
}

# 1) Repo & Token laden
Set-Location (RepoRoot (Get-Location))

$tokFile = Join-Path $env:LOCALAPPDATA 'SmartTScope\gh_pat.txt'
if (-not (Test-Path -LiteralPath $tokFile)) {
  throw "Token-Datei fehlt: $tokFile"
}
$token = (Get-Content -LiteralPath $tokFile -Raw -Encoding ASCII).Trim()
if ($token.Length -lt 30) {
  throw "Token in $tokFile ist zu kurz/unplausibel (Länge: $($token.Length))."
}

# HTTP Basic Header bauen: "username:token" → Base64
$pair  = "tschoenfelder:$token"
$bytes = [Text.Encoding]::ASCII.GetBytes($pair)
$auth  = [Convert]::ToBase64String($bytes)
$hdr   = "AUTHORIZATION: Basic $auth"

# 2) Remote sicher auf HTTPS
Run 'git remote set-url origin https://github.com/tschoenfelder/SmartTScope.git'

# 3) Optional committen
$st = git status --porcelain=v1
if ($CommitMessage -and $st) {
  Run 'git add -A'
  Run ('git -c core.editor=true commit -m "{0}"' -f $CommitMessage)
}

# 4) Netzwerk-Calls IMMER mit http.extraheader (umgeht AskPass & Helper)
Run ('git -c http.extraheader="{0}" fetch origin' -f $hdr)

# 5) Optional: aktuellen Branch → main fast-forward mergen (kein Editor)
$cur = (git rev-parse --abbrev-ref HEAD).Trim()
if ($cur -ne 'main' -and $MergeCurrentToMain) {
  Run 'git switch main'
  Run ('git -c http.extraheader="{0}" pull --ff-only origin main' -f $hdr)
  Run ('git -c http.extraheader="{0}" merge --ff-only {1}' -f $hdr, $cur)
}

# 6) Auf main wechseln & pushen
if ((git rev-parse --abbrev-ref HEAD).Trim() -ne 'main') { Run 'git switch main' }
Run ('git -c http.extraheader="{0}" push -u origin main' -f $hdr)

Write-Host "✅ Push nach origin/main OK"
