@echo off
setlocal
cd /d "%~dp0"
title Cars ATTM - Inicio automatico
echo ================================================
echo              CARS ATTM
echo       Inicio automatico de la aplicacion
echo ================================================
echo.
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0iniciar.ps1"
if errorlevel 1 (
  echo.
  echo No se pudo completar el inicio. Revisa el mensaje anterior.
)
echo.
echo Puedes cerrar esta ventana cuando termine el proceso.
pause
endlocal
