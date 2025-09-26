@echo off
setlocal
if not exist ".git" (
  echo ERROR: Bitte im Repo-Root ausfuehren (hier fehlt .git).
  exit /b 1
)

rem AskPass fest verdrahten
set "GIT_ASKPASS=%~dp0git-askpass.bat"
set "SSH_ASKPASS=%GIT_ASKPASS%"
set GIT_TERMINAL_PROMPT=0

rem Optional committen: 1. Arg = Commit-Message
if not "%~1"=="" (
  git add -A || goto :err
  git -c core.editor=true commit -m "%~1" || goto :err
)

rem Remote/Helper
git remote set-url origin https://github.com/tschoenfelder/SmartTScope.git
git config --local credential.helper "" 1>nul 2>nul

rem Auf main wechseln, holen, pushen
git switch main 1>nul 2>nul
git fetch origin || goto :err
git pull --ff-only origin main || goto :err
git push -u origin main || goto :err

echo OK: Push nach origin/main
exit /b 0

:err
echo ERROR: Befehl fehlgeschlagen (Code %ERRORLEVEL%)
exit /b 1
^Z
