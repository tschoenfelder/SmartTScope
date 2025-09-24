:: scripts\git-askpass.cmd
@echo off
powershell -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0git-askpass.ps1" %*
