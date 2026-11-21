# Publica la interfaz local mediante un Cloudflare Quick Tunnel temporal.
# No abre puertos del router ni expone PostgreSQL/Kafka/APIs al host.
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot

$envFile = Join-Path $PSScriptRoot '.env'
if (-not (Test-Path -LiteralPath $envFile)) {
    throw 'No se encontró .env. Ejecuta este archivo desde la carpeta principal de Cars ATTM.'
}

$portLine = Get-Content -LiteralPath $envFile | Where-Object { $_ -match '^WEB_PORT=' } | Select-Object -Last 1
if (-not $portLine -or $portLine -notmatch '^WEB_PORT=(\d+)$') {
    throw 'No se encontró WEB_PORT válido en .env. Ejecuta primero INICIAR_CARS_ATTM.cmd.'
}
$port = [int]$Matches[1]

$cloudflaredCandidates = @(
    (Join-Path $PSScriptRoot 'tools\cloudflared.exe'),
    'C:\Cloudflared\cloudflared.exe'
)
$command = Get-Command cloudflared.exe -ErrorAction SilentlyContinue
if ($command) { $cloudflaredCandidates += $command.Source }
$cloudflared = $cloudflaredCandidates | Where-Object { $_ -and (Test-Path -LiteralPath $_) } | Select-Object -First 1

if (-not $cloudflared) {
    Write-Host 'No se encontró cloudflared.exe.' -ForegroundColor Yellow
    Write-Host 'Descárgalo desde https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/' -ForegroundColor Cyan
    Write-Host 'Guárdalo en la carpeta tools\cloudflared.exe o en C:\Cloudflared\cloudflared.exe.' -ForegroundColor Cyan
    exit 1
}

$url = "http://127.0.0.1:$port"
try {
    $health = Invoke-WebRequest -Uri "$url/health" -UseBasicParsing -TimeoutSec 5
    if ($health.StatusCode -ne 200) {
        throw "El frontend respondió HTTP $($health.StatusCode) en /health."
    }
}
catch {
    throw "Cars ATTM no responde en $url. Ejecuta primero INICIAR_CARS_ATTM.cmd. Detalle: $($_.Exception.Message)"
}

Write-Host ''
Write-Host 'CARS ATTM - PUBLICACIÓN TEMPORAL' -ForegroundColor Cyan
Write-Host "Frontend local: $url" -ForegroundColor Green
Write-Host 'Cloudflare generará una dirección HTTPS temporal en esta ventana.' -ForegroundColor Green
Write-Host 'No cierres la ventana mientras quieras mantener el acceso externo.' -ForegroundColor Yellow
Write-Host 'La URL temporal es accesible para cualquiera que la conozca; la aplicación seguirá exigiendo inicio de sesión.' -ForegroundColor Yellow
Write-Host 'No utilices datos personales reales ni cobros reales en este modo de demostración.' -ForegroundColor Yellow
Write-Host 'Pulsa Ctrl+C para detener la publicación.' -ForegroundColor Gray
Write-Host ''

& $cloudflared tunnel --url $url
if ($LASTEXITCODE -ne 0) {
    throw "cloudflared terminó con código $LASTEXITCODE. Revisa el mensaje de la herramienta."
}
