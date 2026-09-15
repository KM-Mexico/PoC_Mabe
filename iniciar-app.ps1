[CmdletBinding()]
param(
    [switch]$NoBuild,
    [switch]$NoBrowser
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

if (-not $PSScriptRoot) {
    throw 'No se pudo determinar la carpeta del proyecto.'
}

Set-Location $PSScriptRoot
$tokenWasPrompted = $false

function Stop-WithMessage {
    param([Parameter(Mandatory)][string]$Message)
    Write-Host "`nERROR: $Message" -ForegroundColor Red
    exit 1
}

function Invoke-Docker {
    param([Parameter(Mandatory)][string[]]$Arguments)
    & docker @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Docker terminó con código $LASTEXITCODE."
    }
}

function ConvertTo-PlainText {
    param([Parameter(Mandatory)][Security.SecureString]$SecureValue)
    $pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($SecureValue)
    try {
        return [Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer)
    }
    finally {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer)
    }
}

function Wait-ForDocker {
    if (Get-Command docker -ErrorAction SilentlyContinue) {
        & docker info *> $null
        if ($LASTEXITCODE -eq 0) {
            return
        }
    }

    $dockerDesktop = Join-Path $Env:ProgramFiles 'Docker\Docker\Docker Desktop.exe'
    if (-not (Test-Path $dockerDesktop)) {
        Start-Process 'https://www.docker.com/products/docker-desktop/'
        Stop-WithMessage 'Docker Desktop no está instalado. Se abrió su página oficial; instálalo y vuelve a ejecutar el script.'
    }

    Write-Host 'Iniciando Docker Desktop...' -ForegroundColor Cyan
    Start-Process $dockerDesktop
    foreach ($attempt in 1..90) {
        Start-Sleep -Seconds 2
        & docker info *> $null
        if ($LASTEXITCODE -eq 0) {
            return
        }
    }

    Stop-WithMessage 'Docker Desktop no terminó de iniciar en tres minutos.'
}

function Wait-ForApplication {
    $healthUrl = 'http://localhost:4200/api/v1/health'
    Write-Host 'Esperando a que la aplicación esté saludable...' -ForegroundColor Cyan

    foreach ($attempt in 1..90) {
        try {
            $health = Invoke-RestMethod -Uri $healthUrl -Method Get -TimeoutSec 3
            if ($health.status -eq 'ok' -and $health.mocks_enabled -eq $false) {
                return
            }
        }
        catch {
            # Es normal mientras Docker termina de iniciar los servicios.
        }
        Start-Sleep -Seconds 2
    }

    Write-Host "`nEstado de los contenedores:" -ForegroundColor Yellow
    & docker compose ps
    Write-Host "`nÚltimos registros:" -ForegroundColor Yellow
    & docker compose logs --tail 80 api web
    Stop-WithMessage 'La aplicación no quedó saludable o intentó arrancar con generación simulada.'
}

function Show-DockerDiagnostics {
    Write-Host "`nDiagnóstico de Docker Compose:" -ForegroundColor Yellow
    & docker compose ps
    Write-Host "`nLogs del backend (api):" -ForegroundColor Yellow
    & docker compose logs --tail 200 api
    Write-Host "`nLogs del frontend (web):" -ForegroundColor Yellow
    & docker compose logs --tail 100 web
}

Write-Host '============================================================' -ForegroundColor DarkCyan
Write-Host '  Casecraft - Inicio local con agente real' -ForegroundColor Cyan
Write-Host '============================================================' -ForegroundColor DarkCyan

if (-not (Test-Path 'docker-compose.yml') -and -not (Test-Path 'compose.yaml')) {
    Stop-WithMessage 'Ejecuta este script desde la raíz del proyecto, junto al archivo de Docker Compose.'
}

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    $dockerDesktop = Join-Path $Env:ProgramFiles 'Docker\Docker\Docker Desktop.exe'
    $dockerCliDirectory = Join-Path $Env:ProgramFiles 'Docker\Docker\resources\bin'
    $dockerCli = Join-Path $dockerCliDirectory 'docker.exe'
    if (Test-Path $dockerCli) {
        $Env:Path = "$dockerCliDirectory;$Env:Path"
    }
    if (-not (Test-Path $dockerDesktop)) {
        Start-Process 'https://www.docker.com/products/docker-desktop/'
        Stop-WithMessage 'Docker Desktop no está instalado. Se abrió su página oficial.'
    }
}

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Stop-WithMessage 'No se encontró docker.exe. Reinstala Docker Desktop y abre una nueva ventana de PowerShell.'
}

Wait-ForDocker

& docker compose version *> $null
if ($LASTEXITCODE -ne 0) {
    Stop-WithMessage 'Docker Compose v2 no está disponible. Actualiza Docker Desktop.'
}
Write-Host 'Docker Desktop y Compose están disponibles.' -ForegroundColor Green

if ([string]::IsNullOrWhiteSpace($Env:CODEX_API_KEY)) {
    Write-Host "`nEl agente real necesita CODEX_API_KEY." -ForegroundColor Yellow
    $secureToken = Read-Host 'Pega el token (no se mostrará ni se guardará)' -AsSecureString
    $plainToken = ConvertTo-PlainText $secureToken
    if ([string]::IsNullOrWhiteSpace($plainToken)) {
        Stop-WithMessage 'No se proporcionó el token del agente.'
    }
    $Env:CODEX_API_KEY = $plainToken
    $plainToken = $null
    $secureToken.Dispose()
    $tokenWasPrompted = $true
}

try {
    Write-Host "`nLevantando la aplicación..." -ForegroundColor Cyan
    if ($NoBuild) {
        Invoke-Docker -Arguments @('compose', 'up', '--detach')
    }
    else {
        Invoke-Docker -Arguments @('compose', 'up', '--detach', '--build')
    }

    Wait-ForApplication

    Write-Host "`nAplicación lista con el agente real:" -ForegroundColor Green
    Write-Host '  http://localhost:4200' -ForegroundColor White
    Write-Host '  API: http://localhost:8000/api/docs' -ForegroundColor DarkGray
    Write-Host "`nPara detenerla: docker compose down" -ForegroundColor DarkGray

    if (-not $NoBrowser) {
        Start-Process 'http://localhost:4200'
    }
}
catch {
    Show-DockerDiagnostics
    Stop-WithMessage $_.Exception.Message
}
finally {
    if ($tokenWasPrompted) {
        Remove-Item Env:CODEX_API_KEY -ErrorAction SilentlyContinue
    }
}
