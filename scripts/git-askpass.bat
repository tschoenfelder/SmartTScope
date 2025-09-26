@echo off
setlocal ENABLEDELAYEDEXPANSION

rem Persistenter Token-Ort:
set "TOKENFILE=%LOCALAPPDATA%\SmartTScope\gh_pat.txt"

rem Prompt-Text (1. Argument)
set "PROMPT=%~1"
if not defined PROMPT set "PROMPT="

rem Immer Windows-findstr verwenden (kein Unix find aus Git-Bash):
set "FINDSTR=%SystemRoot%\System32\findstr.exe"

echo %PROMPT% | "%FINDSTR%" /I /C:"Username" >nul
if %errorlevel%==0 (
  echo x-access-token
  exit /b 0
)

echo %PROMPT% | "%FINDSTR%" /I /C:"Password" >nul
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
