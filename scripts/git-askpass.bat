@echo off
setlocal ENABLEDELAYEDEXPANSION

rem Pfad zur Token-Datei
set "TOKENFILE=%LOCALAPPDATA%\SmartTScope\gh_pat.txt"

rem Prompt-Text (1. Argument)
set "PROMPT=%~1"
if not defined PROMPT set "PROMPT="

echo %PROMPT% | find /I "Username" >nul
if %errorlevel%==0 (
  echo tschoenfelder
  exit /b 0
)

echo %PROMPT% | find /I "Password" >nul
if %errorlevel%==0 (
  if exist "%TOKENFILE%" (
    set /p TOKEN=<"%TOKENFILE%"
    echo !TOKEN!
    exit /b 0
  ) else (
    exit /b 1
  )
)

exit /b 0
