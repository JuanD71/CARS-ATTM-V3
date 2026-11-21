# Diagnostico no destructivo de Cars ATTM.
$ErrorActionPreference = 'Continue'
Set-Location $PSScriptRoot

Write-Host 'Estado de contenedores:' -ForegroundColor Cyan
docker compose --env-file '.\.env' ps -a

$webPort = 8080
$portLine = Get-Content '.\.env' | Where-Object { $_ -match '^WEB_PORT=(\d+)$' } | Select-Object -Last 1
if ($portLine -match '^WEB_PORT=(\d+)$') { $webPort = [int]$Matches[1] }
$url = "http://localhost:$webPort/login"
Write-Host "`nFrontend esperado: $url" -ForegroundColor Cyan
try {
    $response = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 8
    Write-Host "Frontend: RESPONDE (HTTP $($response.StatusCode))" -ForegroundColor Green
}
catch {
    Write-Host "Frontend: NO RESPONDE ($($_.Exception.Message))" -ForegroundColor Red
}

Write-Host "`nConteo de vehiculos en PostgreSQL:" -ForegroundColor Cyan
docker compose --env-file '.\.env' exec -T inventario-db psql -U inventario -d inventario_db -t -c 'SELECT COUNT(*) FROM vehiculos;'
Write-Host "`nConteo de usuarios en PostgreSQL:" -ForegroundColor Cyan
docker compose --env-file '.\.env' exec -T usuarios-db psql -U usuarios_user -d usuarios_db -t -c 'SELECT COUNT(*) FROM usuarios;'
Write-Host "`nDiagnostico terminado. No se modificaron datos." -ForegroundColor Green
