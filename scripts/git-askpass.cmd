@echo off
setlocal
set PS1=%~dp0git-askpass.ps1
powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "%PS1%" %*
endlocal
