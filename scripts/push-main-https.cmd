@echo off
setlocal ENABLEDELAYEDEXPANSION

rem --- AskPass verdrahten ---
for %%I in ("%~dp0") do set "SCRIPTDIR=%%~fI"
set "GIT_ASKPASS=%SCRIPTDIR%git-askpass.bat"
set "SSH_ASKPASS=%GIT_ASKPASS%"

rem --- Ins Repo-Root wechseln ---
set "HERE=%cd%"
set "ROOT=%HERE%"
:findroot
if exist "%ROOT%\.git" goto rootok
for %%D in ("%ROOT%") do set "ROOT=%%~dpD"
if /I "%ROOT%"=="%HERE%" (
  echo Kein Git-Repo gefunden.
  exit /b 1
)
goto findroot
:rootok
cd /d "%ROOT%"

rem --- Remote auf HTTPS setzen & Credential-Helper abschalten ---
git remote set-url origin https://github.com/tschoenfelder/SmartTScope.git
git config --local credential.helper ""

rem --- Optional committen: 1. Argument = Commit-Message ---
if not "%~1"=="" (
  git add -A || goto :err
  git -c core.editor=true commit -m "%~1" || goto :err
)

rem --- Aktuellen Branch bestimmen ---
for /f "delims=" %%B in ('git rev-parse --abbrev-ref HEAD') do set CUR=%%B

rem --- Fetch ---
git fetch origin || goto :err

rem --- Optional Merge current -> main (Fast-Forward only) bei 2. Arg = -M oder /M ---
set "FLAG=%~2"
if /I "%FLAG%"=="-M"  goto domerge
if /I "%FLAG%"=="/M" goto domerge
goto skipmerge

:domerge
if /I not "%CUR%"=="main" (
  git switch main || goto :err
  git pull --ff-only origin main || goto :err
  git merge --ff-only "%CUR%" || goto :err
)

:skipmerge
rem --- Auf main wechseln & pushen ---
for /f "delims=" %%B in ('git rev-parse --abbrev-ref HEAD') do set CUR=%%B
if /I not "%CUR%"=="main" git switch main || goto :err

git push -u origin main || goto :err

echo OK: Push nach origin/main
exit /b 0

:err
echo ERROR: Befehl fehlgeschlagen (Code %ERRORLEVEL%)
exit /b 1
