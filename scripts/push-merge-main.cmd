@echo off
set "GIT_ASKPASS=%~dp0git-askpass.bat"
set "SSH_ASKPASS=%GIT_ASKPASS%"
set GIT_TERMINAL_PROMPT=0

if "%~1"=="" (
  echo Usage: %~nx0 FEATURE_BRANCH
  exit /b 2
)

git switch main || goto :err
git fetch origin || goto :err
git pull --ff-only origin main || goto :err
git merge --ff-only "%~1" || goto :err
git push -u origin main || goto :err
echo OK: Merge+Push main
exit /b 0

:err
echo ERROR: Merge/Push fehlgeschlagen (Code %ERRORLEVEL%)
exit /b 1
