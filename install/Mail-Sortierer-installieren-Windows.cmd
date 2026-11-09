@echo off
chcp 65001 >nul
echo Mail-Sortierer wird installiert ...
powershell -NoProfile -ExecutionPolicy Bypass -Command "irm https://raw.githubusercontent.com/felixwrk/mail-sortierer/main/install/windows.ps1 | iex"
echo.
pause
