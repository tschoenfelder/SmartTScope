# scripts/git-askpass.ps1
param([string]$Prompt = "")

# Fallback: Token aus Datei %LOCALAPPDATA%\SmartTScope\gh_pat.txt
$TokenPath = Join-Path $env:LOCALAPPDATA 'SmartTScope\gh_pat.txt'

function Get-Token {
  if (-not [string]::IsNullOrWhiteSpace($env:GITHUB_TOKEN)) { return $env:GITHUB_TOKEN }
  if (Test-Path -LiteralPath $TokenPath) {
    try {
      $t = Get-Content -LiteralPath $TokenPath -Raw -Encoding ASCII
      return ($t -replace '\s+$','')
    } catch { }
  }
  return $null
}

if ($Prompt -match 'Username') {
  'tschoenfelder'
  exit 0
}

if ($Prompt -match 'Password') {
  $tok = Get-Token
  if ($tok) { $tok; exit 0 }
  # kein Token -> Git soll scheitern
  exit 1
}

exit 0
