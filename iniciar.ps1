# Cars ATTM - iniciador automatico para Windows 10/11.
# No detiene contenedores ajenos ni elimina volumenes/bases de datos.
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$envFile = Join-Path $PSScriptRoot '.env'
$composeFile = Join-Path $PSScriptRoot 'docker-compose.yml'
$composeArgs = @('--project-directory', $PSScriptRoot, '--env-file', $envFile)

function Write-Step([string]$Message) {
    Write-Host "`n==> $Message" -ForegroundColor Cyan
}

function Invoke-Compose {
    param([string[]]$DockerArgs)
    & docker compose @composeArgs @DockerArgs
    if ($LASTEXITCODE -ne 0) {
        throw "Fallo docker compose $($DockerArgs -join ' ') (codigo $LASTEXITCODE)."
    }
}

function Test-DockerReady {
    & docker info *> $null
    return ($LASTEXITCODE -eq 0)
}

function Test-PortAvailable([int]$Port) {
    # No selecciona puertos que ya esten publicados por otro contenedor Docker.
    $published = & docker ps --filter "publish=$Port" --format '{{.ID}}' 2>$null
    if ($LASTEXITCODE -eq 0 -and $published) { return $false }

    # Comprueba tambien los procesos que escuchan directamente en Windows.
    $listener = $null
    try {
        $listener = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback, $Port)
        $listener.Start()
        return $true
    }
    catch { return $false }
    finally {
        if ($null -ne $listener) { try { $listener.Stop() } catch {} }
    }
}

function Get-FrontendHostPort([string]$ContainerId) {
    # No usa `docker port`: ese comando devuelve un error cuando el contenedor
    # existe pero todavia no tiene un puerto publicado. Inspect permite tratarlo
    # como una condicion normal y continuar con la reparacion automatica.
    if ([string]::IsNullOrWhiteSpace($ContainerId)) { return $null }
    $jsonText = & docker inspect --format '{{json .NetworkSettings.Ports}}' $ContainerId 2>$null
    if ($LASTEXITCODE -ne 0 -or -not $jsonText) { return $null }
    try {
        $portMap = ($jsonText | Out-String | ConvertFrom-Json -ErrorAction Stop)
        $property = $portMap.PSObject.Properties['80/tcp']
        if ($null -eq $property -or $null -eq $property.Value) { return $null }
        $bindings = @($property.Value)
        if ($bindings.Count -lt 1) { return $null }
        $hostPort = 0
        if ([int]::TryParse([string]$bindings[0].HostPort, [ref]$hostPort) -and $hostPort -gt 0) {
            return $hostPort
        }
    }
    catch { return $null }
    return $null
}

function Set-EnvValue([string]$Name, [string]$Value) {
    $lines = [System.Collections.Generic.List[string]]::new()
    if (Test-Path -LiteralPath $envFile) {
        foreach ($line in [System.IO.File]::ReadAllLines($envFile)) { $lines.Add($line) }
    }
    $found = $false
    for ($i = 0; $i -lt $lines.Count; $i++) {
        if ($lines[$i] -match ('^' + [regex]::Escape($Name) + '=')) {
            $lines[$i] = "$Name=$Value"
            $found = $true
        }
    }
    if (-not $found) { $lines.Add("$Name=$Value") }
    $utf8NoBom = [System.Text.UTF8Encoding]::new($false)
    [System.IO.File]::WriteAllLines($envFile, $lines, $utf8NoBom)
}

try {
    Write-Host '================================================' -ForegroundColor DarkCyan
    Write-Host '                  CARS ATTM' -ForegroundColor White
    Write-Host '          INICIO AUTOMATICO DE LA APP' -ForegroundColor White
    Write-Host '================================================' -ForegroundColor DarkCyan

    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
        throw 'Docker no esta instalado o no esta disponible en PATH. Instala Docker Desktop.'
    }
    if (-not (Test-Path -LiteralPath $composeFile)) {
        throw 'No encuentro docker-compose.yml. Extrae el ZIP completo y ejecuta este iniciador desde la carpeta principal.'
    }
    if (-not (Test-Path -LiteralPath $envFile)) {
        throw 'No encuentro .env. El ZIP general debe incluirlo junto a docker-compose.yml.'
    }

    # Evita que variables heredadas de otras terminales sobreescriban .env.
    @('USUARIOS_DB_PASSWORD','MULTAS_DB_PASSWORD','INVENTARIO_DB_PASSWORD','ORDENES_DB_PASSWORD','CARRITO_DB_PASSWORD','JWT_SECRET','INTERNAL_API_KEY','WEB_PORT') | ForEach-Object {
        Remove-Item "Env:$_" -ErrorAction SilentlyContinue
    }

    if (-not (Test-DockerReady)) {
        Write-Step 'Docker Desktop no esta listo. Intentando abrirlo...'
        $desktopPaths = @(
            "$Env:ProgramFiles\Docker\Docker\Docker Desktop.exe",
            "$Env:LOCALAPPDATA\Programs\Docker\Docker\Docker Desktop.exe"
        ) | Select-Object -Unique
        $desktopExe = $desktopPaths | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
        if ($desktopExe -and -not (Get-Process -Name 'Docker Desktop' -ErrorAction SilentlyContinue)) {
            Start-Process -FilePath $desktopExe
        }
        $ready = $false
        for ($i = 0; $i -lt 90; $i++) {
            Start-Sleep -Seconds 2
            if (Test-DockerReady) { $ready = $true; break }
        }
        if (-not $ready) {
            throw 'Docker Desktop no respondio en 180 segundos. Abre Docker Desktop, espera a que indique Engine running y vuelve a ejecutar este archivo.'
        }
    }

    Write-Step 'Comprobando si existe un frontend de esta instalacion'
    $webPort = $null
    $existingFrontend = (& docker compose @composeArgs ps -q frontend 2>$null | Select-Object -First 1)
    if ($LASTEXITCODE -eq 0 -and $existingFrontend) {
        $webPort = Get-FrontendHostPort -ContainerId ([string]$existingFrontend).Trim()
        if ($webPort) {
            Write-Host "Frontend existente con puerto publicado: $webPort" -ForegroundColor Green
        }
        else {
            Write-Host 'El frontend existente no tiene puerto publicado. Se recreara automaticamente.' -ForegroundColor Yellow
        }
    }

    if (-not $webPort) {
        Write-Step 'Buscando un puerto web libre en Windows'
        foreach ($candidate in @(8081,8086,8090,8091,8100,8180,8888,18080,18081,18082,8080,8082,8083,8092,8093)) {
            if (Test-PortAvailable -Port $candidate) { $webPort = $candidate; break }
        }
    }
    if (-not $webPort) {
        throw 'No hay puertos web libres en la lista de prueba. Cierra una aplicacion local y vuelve a ejecutar el iniciador.'
    }

    Set-EnvValue -Name 'WEB_PORT' -Value ([string]$webPort)
    $url = "http://localhost:$webPort/"
    Write-Host "Puerto web seleccionado: $webPort" -ForegroundColor Green

    Write-Step 'Validando la configuracion de Docker Compose'
    Invoke-Compose -DockerArgs @('config','--quiet')
    $resolved = (& docker compose @composeArgs config 2>&1 | Out-String)
    if ($LASTEXITCODE -ne 0) { throw 'No se pudo leer la configuracion resuelta de Docker Compose.' }
    if ($resolved -notmatch [regex]::Escape([string]$webPort)) {
        throw "Docker Compose no esta resolviendo WEB_PORT=$webPort. Revisa la seccion ports del frontend."
    }

    Write-Step 'Construyendo e iniciando la plataforma completa'
    Invoke-Compose -DockerArgs @('up','--build','-d')

    # Fuerza la recreacion SOLO del frontend para aplicar WEB_PORT incluso si
    # ya existia un contenedor antiguo creado sin publicacion del puerto 80.
    Write-Step 'Aplicando el puerto web al contenedor frontend'
    Invoke-Compose -DockerArgs @('up','-d','--no-deps','--force-recreate','frontend')
    Start-Sleep -Seconds 3

    $frontendId = (& docker compose @composeArgs ps -q frontend 2>$null | Select-Object -First 1)
    $publishedPort = $null
    if ($frontendId) { $publishedPort = Get-FrontendHostPort -ContainerId ([string]$frontendId).Trim() }

    if (-not $publishedPort) {
        # Un unico segundo intento de recreacion; no modifica bases ni otros servicios.
        Write-Step 'Reintentando la publicacion del puerto del frontend'
        Invoke-Compose -DockerArgs @('up','-d','--no-deps','--force-recreate','frontend')
        Start-Sleep -Seconds 3
        $frontendId = (& docker compose @composeArgs ps -q frontend 2>$null | Select-Object -First 1)
        if ($frontendId) { $publishedPort = Get-FrontendHostPort -ContainerId ([string]$frontendId).Trim() }
    }

    if (-not $publishedPort) {
        Write-Host 'Configuracion de puertos resuelta:' -ForegroundColor Yellow
        & docker compose @composeArgs config
        Write-Host 'Inspeccion del frontend:' -ForegroundColor Yellow
        if ($frontendId) { & docker inspect --format '{{json .NetworkSettings.Ports}}' $frontendId }
        throw 'El frontend arranco, pero Docker no publico el puerto 80 hacia Windows. No se eliminaron datos.'
    }

    $webPort = [int]$publishedPort
    $url = "http://localhost:$webPort/"
    Write-Host "Puerto publicado correctamente: 127.0.0.1:$webPort -> contenedor:80" -ForegroundColor Green

    Write-Step 'Esperando respuesta HTTP del frontend'
    $webReady = $false
    for ($i = 0; $i -lt 75; $i++) {
        try {
            $response = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 5
            if ($response.StatusCode -ge 200 -and $response.StatusCode -lt 500) { $webReady = $true; break }
        }
        catch {}
        Start-Sleep -Seconds 2
    }

    Write-Step 'Estado de los servicios Cars ATTM'
    & docker compose @composeArgs ps

    if ($webReady) {
        Write-Host "`nCARS ATTM ESTA DISPONIBLE: $url" -ForegroundColor Green
        Start-Process $url
    }
    else {
        Write-Host "`nLos contenedores iniciaron, pero la web no respondio en $url." -ForegroundColor Yellow
        Write-Host 'Ultimos registros del frontend:' -ForegroundColor Yellow
        & docker compose @composeArgs logs --tail=100 frontend
        Write-Host "Cuando responda, abre: $url" -ForegroundColor Cyan
        exit 1
    }

    Write-Host "`nPuerto web guardado en .env: $webPort" -ForegroundColor Gray
    Write-Host 'Puedes volver a ejecutar INICIAR_CARS_ATTM.cmd para iniciar la aplicacion.' -ForegroundColor Cyan
    Write-Host 'No se detuvieron contenedores ajenos ni se eliminaron volumenes o bases de datos.' -ForegroundColor Gray
}
catch {
    Write-Host "`nERROR: $($_.Exception.Message)" -ForegroundColor Red
    Write-Host 'No se detuvieron contenedores ajenos ni se eliminaron volumenes o bases de datos.' -ForegroundColor Yellow
    exit 1
}
