@echo on
setlocal ENABLEDELAYEDEXPANSION
if not exist ".git" (echo ERROR: Bitte im Repo-Root ausfuehren (hier fehlt .git).& exit /b 1)
for %%%%I in ("%%~dp0") do set "SCRIPTDIR=%%%%~fI"
set "GIT_ASKPASS=%%SCRIPTDIR%%git-askpass.bat"
set "SSH_ASKPASS=%%GIT_ASKPASS%%"
set GIT_TERMINAL_PROMPT=0
set "TOKENFILE=%C:\Users\U070420\AppData\Local%\SmartTScope\gh_pat.txt"
if not exist "%%TOKENFILE%%" (echo ERROR: Token-Datei fehlt: %%TOKENFILE%%& exit /b 1)
for %%%%A in ("%%TOKENFILE%%") do set TOKSIZE=%%%%~zA
if not defined TOKSIZE set TOKSIZE=0
if %%TOKSIZE%% LSS 30 (echo ERROR: Token zu kurz (%%TOKSIZE%% Bytes).& exit /b 1)
git remote set-url origin https://github.com/tschoenfelder/SmartTScope.git
git config --local credential.helper ""
if not "%%~1"=="" (
  git add -A || goto :err
  git -c core.editor=true commit -m "%%~1" || goto :err
)
for /f "delims=" %%%%B in ('git rev-parse --abbrev-ref HEAD') do set CUR=%%%%B
git fetch origin || goto :err
set "FLAG=%%~2"
if /I "%%FLAG%%"=="-M" if /I not "%%CUR%%"=="main" (
  git switch main || goto :err
  git pull --ff-only origin main || goto :err
  git merge --ff-only "%%CUR%%" || goto :err
)
for /f "delims=" %%%%B in ('git rev-parse --abbrev-ref HEAD') do set CUR=%%%%B
if /I not "%%CUR%%"=="main" git switch main || goto :err
git push -u origin main || goto :err
echo OK: Push nach origin/main
exit /b 0
:err
echo ERROR: Befehl fehlgeschlagen (Code %0%)
exit /b 1
