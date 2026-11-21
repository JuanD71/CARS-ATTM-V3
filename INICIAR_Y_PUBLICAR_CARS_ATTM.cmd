@echo off
setlocal
cd /d "%~dp0"
title Cars ATTM - Inicio y publicacion web

echo ================================================
echo          CARS ATTM - WEB TEMPORAL
echo ================================================
echo.

powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0iniciar.ps1"
if errorlevel 1 (
  echo.
  echo No se pudo iniciar Cars ATTM. No se publicara.
  pause
  exit /b 1
)

powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0publicar.ps1"
if errorlevel 1 (
  echo.
  echo No se pudo publicar Cars ATTM.
  pause
  exit /b 1
)
endlocal
