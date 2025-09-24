# scripts/git-askpass.ps1
param([string]$Prompt)
if ($Prompt -like "*Username*") { [Console]::Out.Write("tschoenfelder"); exit 0 }
if ($Prompt -like "*Password*") {
  if ($env:GITHUB_TOKEN) { [Console]::Out.Write($env:GITHUB_TOKEN); exit 0 }
  Write-Error "GITHUB_TOKEN nicht gesetzt"; exit 1
}
# Fallback
[Console]::Out.Write(""); exit 0
