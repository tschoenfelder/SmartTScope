# Pfad zu true.exe ermitteln (typische Installationsorte)
$trueExe = @(
  "$env:ProgramFiles\Git\usr\bin\true.exe",
  "$env:ProgramFiles(x86)\Git\usr\bin\true.exe"
) | Where-Object { Test-Path $_ } | Select-Object -First 1

if (-not $trueExe) { throw "Konnte true.exe nicht finden. Ist Git in 'C:\Program Files\Git' installiert?" }

git config --local core.editor "$trueExe"
git config --local sequence.editor "$trueExe"

# Mergetool-Interaktivität sicherheitshalber aus (optional, schadlos)
git config --local --unset-all merge.tool 2>$null
git config --local --unset-all mergetool.prompt 2>$null
git config --local --unset-all difftool.prompt 2>$null
git config --local --unset-all diff.external 2>$null
