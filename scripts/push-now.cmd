@echo off
rem --- AskPass fest verdrahten ---
set "GIT_ASKPASS=%~dp0git-askpass.bat"
set "SSH_ASKPASS=%GIT_ASKPASS%"
set GIT_TERMINAL_PROMPT=0

rem --- Nur committen, wenn Änderungen da sind ---
git diff --quiet && git diff --cached --quiet
if errorlevel 1 (
  git add -A || goto :err
  if "%~1"=="" (
    git -c core.editor=true commit -m "chore: sync" || goto :err
  ) else (
    git -c core.editor=true commit -m "%*" || goto :err
  )
)

rem --- Push nach main ---
git push -u origin main || goto :err
echo OK: Push done
exit /b 0

:err
echo ERROR: Git-Befehl fehlgeschlagen (Code %ERRORLEVEL%)
exit /b 1
