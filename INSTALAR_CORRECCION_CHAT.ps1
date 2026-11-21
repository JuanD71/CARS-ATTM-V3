param([string]$Proyecto)
$ErrorActionPreference = 'Stop'
if ([string]::IsNullOrWhiteSpace($Proyecto)) { $Proyecto = $PSScriptRoot }
$Proyecto = [System.IO.Path]::GetFullPath($Proyecto.Trim().Trim([char]34))
$relative = 'frontend/Services/VehicleConversationService.cs'
$target = Join-Path $Proyecto $relative
$source = Join-Path $PSScriptRoot 'VehicleConversationService.cs'

try {
    Write-Host "`nCARS ATTM - Correccion de preguntas de seguimiento" -ForegroundColor Cyan
    Write-Host "Proyecto: $Proyecto"
    if (!(Test-Path -LiteralPath (Join-Path $Proyecto 'docker-compose.yml'))) {
        throw 'Coloca el parche en la carpeta principal del proyecto, junto a docker-compose.yml.'
    }
    if (!(Test-Path -LiteralPath $target)) {
        throw 'No encuentro VehicleConversationService.cs. Debes tener instalado el chat conversacional anterior.'
    }
    if (!(Test-Path -LiteralPath $source)) {
        throw 'El archivo de correccion no esta junto al instalador. Extrae el ZIP completo.'
    }
    $current = [System.IO.File]::ReadAllText($target, [System.Text.Encoding]::UTF8)
    if (!$current.Contains('public sealed class VehicleConversationService') -or
        !$current.Contains('private static VehicleChatReply ExplainComparison(')) {
        throw 'El servicio actual tiene una estructura diferente. No se modificara para evitar incompatibilidades.'
    }
    $backup = Join-Path $Proyecto ('COPIA_SEGURIDAD_CHAT_COMPARACIONES_' + (Get-Date -Format 'yyyyMMdd_HHmmss'))
    New-Item -ItemType Directory -Path $backup -Force | Out-Null
    Copy-Item -LiteralPath $target -Destination (Join-Path $backup 'VehicleConversationService.cs') -Force
    Copy-Item -LiteralPath $source -Destination $target -Force
    Write-Host "Copia de seguridad: $backup" -ForegroundColor Yellow
    Write-Host 'Actualizado el servicio conversacional. Compilando solo frontend...' -ForegroundColor Cyan
    Push-Location $Proyecto
    try {
        & docker compose --env-file .env up -d --no-deps --build frontend
        if ($LASTEXITCODE -ne 0) { throw 'La compilacion de frontend fallo.' }
        Write-Host "`nCORRECCION INSTALADA. Pulsa Ctrl+F5 en CARS ATTM." -ForegroundColor Green
        Write-Host 'No se modificaron datos, reservas ni microservicios.' -ForegroundColor Green
    }
    catch {
        Write-Host "`nError al compilar. Restaurando automaticamente el servicio anterior..." -ForegroundColor Red
        Copy-Item -LiteralPath (Join-Path $backup 'VehicleConversationService.cs') -Destination $target -Force
        & docker compose --env-file .env up -d --no-deps --build frontend
        if ($LASTEXITCODE -ne 0) {
            Write-Host 'La recompilacion anterior tambien fallo. Revisa Docker Desktop.' -ForegroundColor Red
        }
        throw 'Correccion revertida. Copia el error anterior de la consola.'
    }
    finally { Pop-Location }
}
catch {
    Write-Host "ERROR: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}
