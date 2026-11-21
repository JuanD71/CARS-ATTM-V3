@echo off
setlocal
cd /d "%~dp0"
title Cars ATTM - Publicar en Internet
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0publicar.ps1"
if errorlevel 1 (
  echo.
  echo No se pudo iniciar Cloudflare Tunnel. Revisa el mensaje anterior.
  pause
)
endlocal
