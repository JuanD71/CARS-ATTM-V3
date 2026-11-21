@echo off
setlocal
cd /d "%~dp0"
title CARS ATTM - Corregir comparaciones con IA
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0INSTALAR_CORRECCION_CHAT.ps1"
if errorlevel 1 (
  echo.
  echo La correccion no se aplico. Revisa el error mostrado arriba.
  pause
  exit /b 1
)
echo.
echo Abre el chat y vuelve a probar la pregunta de seguimiento.
pause
endlocal
