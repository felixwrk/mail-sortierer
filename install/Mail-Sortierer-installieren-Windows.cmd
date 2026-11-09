@echo off
chcp 65001 >nul
echo Mail-Sortierer wird installiert ...
powershell -NoProfile -ExecutionPolicy Bypass -Command "irm https://raw.githubusercontent.com/__REPO__/main/install/windows.ps1 | iex"
echo.
pause
