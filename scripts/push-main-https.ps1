# scripts/push-main-https.ps1
[CmdletBinding()]
param([string]$CommitMessage, [switch]$MergeCurrentToMain)

$env:GIT_MERGE_AUTOEDIT = "no"
$ErrorActionPreference = 'Stop'
$env:GIT_EDITOR = $trueExe
$env:GIT_SEQUENCE_EDITOR = $trueExe
$env:VISUAL = $trueExe
$env:EDITOR = $trueExe


function Resolve-RepoRoot([string]$startDir) {
  $d = (Resolve-Path -LiteralPath $startDir).Path
  while ($true) {
    if (Test-Path (Join-Path $d ".git")) { return $d }
    $p = Split-Path $d -Parent
    if ($p -eq $d) { break }; $d = $p
  } ; throw "Kein Git-Repo gefunden."
}

Set-Location (Resolve-RepoRoot (Get-Location))

# Remote sicher auf HTTPS
git remote set-url origin https://github.com/tschoenfelder/SmartTScope.git 2>$null

# ASKPASS: auf CMD-SHIM zeigen (nicht auf .ps1!)
$ask = Join-Path $PSScriptRoot "git-askpass.cmd"
$env:GIT_ASKPASS = $ask
$env:SSH_ASKPASS = $ask  # fallback
$env:GIT_MERGE_AUTOEDIT = 'no'  # Editor bei Auto-Merges unterdrücken

# Optional committen
$st = git status --porcelain=v1
if ($CommitMessage -and $st) {
  git add -A
  git -c core.editor=true commit -m $CommitMessage
}


git fetch origin

# Optional: aktuellen Branch -> main mergen (ohne irgendeinen Editor)
$cur = (git rev-parse --abbrev-ref HEAD).Trim()
if ($cur -ne 'main' -and $MergeCurrentToMain) {
  $feature = $cur
  git switch main
  git pull --ff-only origin main
  git -c core.editor=true -c sequence.editor=true merge --ff-only $feature
}

# Auf main wechseln & pushen
if ((git rev-parse --abbrev-ref HEAD).Trim() -ne 'main') { git switch main }
git push -u origin main

Write-Host "✅ Push nach origin/main OK"
