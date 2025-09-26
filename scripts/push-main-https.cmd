@echo off
setlocal enabledelayedexpansion
if not exist ".git" echo ERROR: Bitte im Repo-Root ausfuehren (hier fehlt .git).& exit /b 1
set "GIT_ASKPASS=%%~dp0git-askpass.bat"
set "SSH_ASKPASS=%C:\Users\U070420\OneDrive - Lufthansa Group\Local Documents\SmartTScope\scripts\git-askpass.bat%"
set GIT_TERMINAL_PROMPT=0
git config --local credential.helper "" 1>nul 2>nul
if not "%%~1"=="" git add -A && git -c core.editor=true commit -m "%%~1"
for /f "delims=" %%%%B in ('git rev-parse --abbrev-ref HEAD') do set CUR=%%%%B
if /i not "%%CUR%%"=="main" git switch main || exit /b 1
git fetch origin || exit /b 1
git pull --ff-only origin main || exit /b 1
git push -u origin main || exit /b 1
echo OK: Push nach origin/main
exit /b 0
