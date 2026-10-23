<#
.SYNOPSIS
    Reproducible isolated container stack for M2-CORE-INT-001 Phase A.

.DESCRIPTION
    Builds and runs a real cross-container stack - PostgreSQL 16, Redis, API,
    business worker and scheduler as separate containers on one user-defined
    network, sharing one writable wordbook volume. No compose support is
    assumed: the local WSL container CLI ("wslc") is used directly.

    Runtime secrets are generated for the throwaway local stack and written to
    <EvidenceRoot>/runtime/runtime.env, which lives outside the code repository.
    Nothing secret is committed.

.PARAMETER Action
    up      build images, create network/volume, start everything
    reset   drop and rebuild the database, flush Redis, wipe the volume
    down    stop and remove every container created by this script

.PARAMETER RuntimeRoot
    Session temp directory that holds the generated runtime env file. It lives
    outside both the code repository and the evidence tree so that disposable
    local credentials are never committed or archived.
#>
[CmdletBinding()]
param(
    [ValidateSet('up', 'reset', 'down')]
    [string]$Action = 'up',
    [string]$RuntimeRoot = 'E:\agent workspace\英语学习工具\ai-workspace\10-collaboration\sessions\A30-TEST\temp\m3ai-runtime',
    [string]$RepoRoot = 'E:\agent workspace\英语学习工具\worktrees\A30-TEST'
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$Network = 'a30-m3-ai-net'
$Volume = 'a30-m3-ai-wordbooks'
$PgVolume = 'a30-m3-ai-pgdata'
$ApiImage = 'a30-m3-ai-api:local'
$FrontendImage = 'a30-m3-ai-frontend:local'
$ProxyImage = 'a30-m3-ai-reverse-proxy:local'
$ProviderImage = 'a30-m3-ai-provider:local'

$Names = [ordered]@{
    pg        = 'a30-m3-ai-pg'
    redis     = 'a30-m3-ai-redis'
    api       = 'a30-m3-ai-api'
    worker    = 'a30-m3-ai-worker'
    scheduler = 'a30-m3-ai-scheduler'
    frontend  = 'a30-m3-ai-frontend'
    proxy     = 'a30-m3-ai-proxy'
    provider  = 'a30-m3-ai-provider'
}

$RuntimeDir = $RuntimeRoot
$EnvFile = Join-Path $RuntimeDir 'runtime.env'

function Invoke-Wslc {
    param([string[]]$Arguments)
    & wslc @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "wslc $($Arguments -join ' ') failed with exit code $LASTEXITCODE"
    }
}

function Ensure-EnvFile {
    if (Test-Path -LiteralPath $EnvFile) { return }
    New-Item -ItemType Directory -Force -Path $RuntimeDir | Out-Null
    $jwt = 'a30-m3-ai-jwt-' + [guid]::NewGuid().ToString('N')
    $pepper = 'a30-m3-ai-pepper-' + [guid]::NewGuid().ToString('N')
    $enc = 'a30-m3-ai-enc-' + [guid]::NewGuid().ToString('N')
    $dbPassword = 'm2core-' + [guid]::NewGuid().ToString('N')
    $adminPassword = 'Qa-M2Core-' + [guid]::NewGuid().ToString('N') + '!x'
    $lines = @(
        'APP_ENV=test'
        'APP_BASE_URL=http://127.0.0.1:8092'
        'FRONTEND_BASE_URL=http://127.0.0.1:8092'
        'CORS_ORIGINS=http://127.0.0.1:8092,http://127.0.0.1:8093,http://127.0.0.1:4180'
        'LOG_LEVEL=INFO'
        'POSTGRES_USER=english_learn'
        "POSTGRES_PASSWORD=$dbPassword"
        'POSTGRES_DB=english_learn_m3ai'
        "DATABASE_URL=postgresql+asyncpg://english_learn:$dbPassword@postgres:5432/english_learn_m3ai"
        'REDIS_URL=redis://redis:6379/0'
        "JWT_SECRET=$jwt"
        "REFRESH_TOKEN_PEPPER=$pepper"
        "SECRET_ENCRYPTION_KEY=$enc"
        'WORDBOOK_STORAGE_DIR=/app/var/wordbooks'
        'AI_ALLOW_PRIVATE_PROVIDER_URLS=true'
        'AI_PROVIDER_RETRY_BACKOFF_SECONDS=0.05'
        'AI_DAILY_QUESTION_GENERATION=20'
        'AI_DAILY_SUBJECTIVE_GRADING=50'
        "QA_BOOTSTRAP_ADMIN_PASSWORD=$adminPassword"
    )
    Set-Content -LiteralPath $EnvFile -Value $lines -Encoding ascii
}

function Get-EnvValue {
    param([string]$Key)
    $match = Get-Content -LiteralPath $EnvFile | Where-Object { $_ -like "$Key=*" }
    return ($match -split '=', 2)[1]
}

function Wait-Ready {
    param([string]$Url, [int]$TimeoutSeconds = 90)
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        try {
            $response = Invoke-RestMethod -Uri $Url -TimeoutSec 5
            if ($response.status -eq 'ready') { return $response }
        } catch {
            Start-Sleep -Milliseconds 700
        }
    }
    throw "Service at $Url did not become ready within $TimeoutSeconds seconds"
}

function Start-Database {
    Invoke-Wslc @(
        'run', '-d', '--name', $Names.pg, '--network', $Network, '--network-alias', 'postgres',
        '-v', "${PgVolume}:/var/lib/postgresql/data", '--env-file', $EnvFile,
        '-p', '127.0.0.1:55444:5432', 'postgres:16-alpine'
    ) | Out-Null
    for ($i = 0; $i -lt 60; $i++) {
        & wslc exec $Names.pg pg_isready -U english_learn -d english_learn_m3ai 2>$null | Out-Null
        if ($LASTEXITCODE -eq 0) { return }
        Start-Sleep -Seconds 1
    }
    throw 'PostgreSQL did not accept connections'
}

function Start-Redis {
    Invoke-Wslc @(
        'run', '-d', '--name', $Names.redis, '--network', $Network, '--network-alias', 'redis', '-p', '127.0.0.1:55445:6379', 'redis:7.0.15'
    ) | Out-Null
    for ($i = 0; $i -lt 30; $i++) {
        & wslc exec $Names.redis redis-cli ping 2>$null | Out-Null
        if ($LASTEXITCODE -eq 0) { return }
        Start-Sleep -Seconds 1
    }
    throw 'Redis did not become ready'
}

function Start-Provider {
    Invoke-Wslc @(
        'run', '-d', '--name', $Names.provider, '--network', $Network, '--network-alias', 'provider',
        '-p', '127.0.0.1:18081:18080', $ProviderImage
    ) | Out-Null
    for ($i = 0; $i -lt 30; $i++) {
        try {
            $probe = Invoke-WebRequest -Uri 'http://127.0.0.1:18081/healthz' -TimeoutSec 3
            if ($probe.StatusCode -eq 200) { return }
        } catch {
            Start-Sleep -Milliseconds 300
        }
    }
    throw 'Controlled provider did not become ready'
}

function Invoke-Migrations {
    Invoke-Wslc @(
        'run', '--rm', '--network', $Network, '--env-file', $EnvFile, $ApiImage, 'alembic', 'upgrade', 'head'
    ) | Out-Null
}

function Invoke-Bootstrap {
    $adminPassword = Get-EnvValue 'QA_BOOTSTRAP_ADMIN_PASSWORD'
    # The CLI refuses to bootstrap while an active administrator exists, so this
    # step is intentionally idempotent: an existing admin is not an error.
    $output = & wslc @(
        'run', '--rm', '--network', $Network, '--env-file', $EnvFile,
        '-e', 'BOOTSTRAP_ADMIN_USERNAME=qa_m3_ai_admin',
        '-e', 'BOOTSTRAP_ADMIN_DISPLAY_NAME=QA M3 AI Admin',
        '-e', "BOOTSTRAP_ADMIN_PASSWORD=$adminPassword",
        $ApiImage, 'python', '-m', 'app.cli', 'bootstrap-admin'
    ) 2>&1 | Out-String
    if ($LASTEXITCODE -ne 0 -and $output -notmatch 'ADMIN_ALREADY_EXISTS|already exists') {
        throw "bootstrap-admin failed: $output"
    }
}

function Start-Application {
    Invoke-Wslc @(
        'run', '-d', '--name', $Names.api, '--network', $Network, '--network-alias', 'api',
        '--env-file', $EnvFile, '-v', "${Volume}:/app/var/wordbooks",
        '-p', '127.0.0.1:8092:8000', $ApiImage
    ) | Out-Null
    Invoke-Wslc @(
        'run', '-d', '--name', $Names.worker, '--network', $Network, '--env-file', $EnvFile,
        '-v', "${Volume}:/app/var/wordbooks", $ApiImage, 'arq', 'app.workers.worker.WorkerSettings'
    ) | Out-Null
    Invoke-Wslc @(
        'run', '-d', '--name', $Names.scheduler, '--network', $Network, '--env-file', $EnvFile,
        '-v', "${Volume}:/app/var/wordbooks", $ApiImage, 'arq', 'app.workers.scheduler.SchedulerSettings'
    ) | Out-Null
    Invoke-Wslc @(
        'run', '-d', '--name', $Names.frontend, '--network', $Network, '--network-alias', 'frontend',
        $FrontendImage
    ) | Out-Null
    Invoke-Wslc @(
        'run', '-d', '--name', $Names.proxy, '--network', $Network, '--network-alias', 'proxy',
        '-p', '127.0.0.1:8093:8080', $ProxyImage
    ) | Out-Null
    for ($i = 0; $i -lt 60; $i++) {
        try {
            $probe = Invoke-WebRequest -Uri 'http://127.0.0.1:8093/healthz' -TimeoutSec 3
            if ($probe.StatusCode -eq 200) { break }
        } catch {
            Start-Sleep -Milliseconds 700
        }
    }
    Wait-Ready -Url 'http://127.0.0.1:8092/health/ready' | Out-Null
}

function Remove-Stack {
    foreach ($name in $Names.Values) {
        & wslc rm -f $name 2>$null | Out-Null
    }
}

switch ($Action) {
    'up' {
        Ensure-EnvFile
        & wslc network create $Network 2>$null | Out-Null
        & wslc volume create $Volume 2>$null | Out-Null
        & wslc volume create $PgVolume 2>$null | Out-Null
        Push-Location $RepoRoot
        try {
            Invoke-Wslc @(
                'build', '-t', $ApiImage, '-f', 'deploy/backend/Dockerfile', '--progress', 'plain', '.'
            ) | Out-Null
            Invoke-Wslc @(
                'build', '-t', $FrontendImage, '-f', 'deploy/frontend/Dockerfile', '--progress', 'plain', '.'
            ) | Out-Null
            Invoke-Wslc @(
                'build', '-t', $ProxyImage, '-f', 'deploy/reverse-proxy/Dockerfile', '--progress', 'plain', '.'
            ) | Out-Null
            Invoke-Wslc @(
                'build', '-t', $ProviderImage, '-f', 'tests/m3-ai-int/fake_provider/Dockerfile', 'tests/m3-ai-int/fake_provider'
            ) | Out-Null
        } finally {
            Pop-Location
        }
        Remove-Stack
        Start-Database
        Start-Redis
        Start-Provider
        Invoke-Migrations
        Invoke-Bootstrap
        Start-Application
        Write-Host 'STACK=READY'
    }
    'reset' {
        if (-not (Test-Path -LiteralPath $EnvFile)) { throw "Missing $EnvFile; run -Action up first" }
        foreach ($name in @($Names.api, $Names.worker, $Names.scheduler)) {
            & wslc stop $name 2>$null | Out-Null
        }
        Start-Sleep -Seconds 2
        Invoke-Wslc @(
            'exec', $Names.pg, 'psql', '-U', 'english_learn', '-d', 'postgres',
            '-c', 'DROP DATABASE IF EXISTS english_learn_m3ai WITH (FORCE);'
        ) | Out-Null
        Invoke-Wslc @(
            'exec', $Names.pg, 'psql', '-U', 'english_learn', '-d', 'postgres',
            '-c', 'CREATE DATABASE english_learn_m3ai OWNER english_learn;'
        ) | Out-Null
        Invoke-Wslc @('exec', $Names.redis, 'redis-cli', '-n', '0', 'flushall') | Out-Null
        # Clear the shared volume with a throwaway container: the worker is stopped
        # at this point, and exec into a stopped container is not supported.
        Invoke-Wslc @(
            'run', '--rm', '--network', $Network, '--env-file', $EnvFile,
            '-v', "${Volume}:/app/var/wordbooks", $ApiImage,
            'sh', '-lc', 'find /app/var/wordbooks -mindepth 1 -delete'
        ) | Out-Null
        Invoke-Migrations
        Invoke-Bootstrap
        if (-not (wslc ps --format json | Select-String $Names.provider)) { Start-Provider }
        foreach ($name in @($Names.api, $Names.worker, $Names.scheduler)) {
            & wslc start $name | Out-Null
        }
        Wait-Ready -Url 'http://127.0.0.1:8092/health/ready' | Out-Null
        Write-Host 'STACK=RESET'
    }
    'down' {
        Remove-Stack
        Write-Host 'STACK=DOWN'
    }
}
