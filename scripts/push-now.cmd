@echo off
rem --- AskPass fest verdrahten (liesst Token aus gh_pat.txt via git-askpass.bat) ---
set "GIT_ASKPASS=%~dp0git-askpass.bat"
set "SSH_ASKPASS=%GIT_ASKPASS%"
set GIT_TERMINAL_PROMPT=0

rem --- Credential-Helper lokal aus ---
git config --local credential.helper "" 1>nul 2>nul

rem --- Commit mit kompletter Message aus allen Argumenten ---
git add -A
git -c core.editor=true commit -m "%*"

rem --- Push auf origin/main (nur ausfuehren, wenn du gerade auf main bist) ---
git push -u origin main

echo OK: Push done
exit /b 0
^Z
