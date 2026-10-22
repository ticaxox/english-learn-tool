<#
.SYNOPSIS
    Runs the M2-CORE-INT-001 Phase A live API acceptance suite.

.DESCRIPTION
    Reads the disposable local credentials from the generated runtime env file
    (kept in the agent session temp directory, never in Git) and drives the real
    containerized stack over HTTP.

.PARAMETER RunId
    Evidence directory name under results/. Reusing an id overwrites that evidence.

.PARAMETER LogFile
    Optional path that additionally receives the raw console output.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$RunId,
    [string]$LogFile,
    [string]$RuntimeEnv = 'E:\agent workspace\英语学习工具\ai-workspace\10-collaboration\sessions\A30-TEST\temp\m2core-runtime\runtime.env',
    [string]$EvidenceDir = 'E:\agent workspace\英语学习工具\ai-workspace\04-qa\evidence\M2-CORE-INT-001',
    [string]$RepoRoot = 'E:\agent workspace\英语学习工具\worktrees\A30-TEST'
)

$ErrorActionPreference = 'Stop'
if (-not (Test-Path -LiteralPath $RuntimeEnv)) { throw "Missing runtime env file: $RuntimeEnv" }

$settings = @{}
foreach ($line in Get-Content -LiteralPath $RuntimeEnv) {
    if ($line -match '^([A-Z0-9_]+)=(.*)$') { $settings[$Matches[1]] = $Matches[2] }
}

$dbUrl = $settings['DATABASE_URL'] -replace '^postgresql\+asyncpg://', 'postgresql://' `
    -replace '@postgres:5432/', '@127.0.0.1:55441/'

$env:PYTHONIOENCODING = 'utf-8'
$env:LIVE_API_BASE_URL = 'http://127.0.0.1:8090'
$env:LIVE_PG_DSN = $dbUrl
$env:EVIDENCE_DIR = $EvidenceDir
$env:LIVE_ADMIN_USERNAME = 'qa_m2core_admin'
$env:LIVE_ADMIN_PASSWORD = $settings['QA_BOOTSTRAP_ADMIN_PASSWORD']
$env:LIVE_MEMBER_USERNAME = 'qa_m2core_member'
# Synthetic fixture credential for the disposable local QA member account only.
$env:LIVE_MEMBER_PASSWORD = 'Qa-M2Core-Member-2026!x'
$env:LIVE_RUN_ID = $RunId

$python = Join-Path $RepoRoot 'backend\.venv\Scripts\python.exe'
$runner = Join-Path $RepoRoot 'tests\m2-core-int\api_e2e.py'
Push-Location $RepoRoot
try {
    if ($LogFile) {
        & $python $runner 2>&1 | Tee-Object -FilePath $LogFile
    } else {
        & $python $runner
    }
    $code = $LASTEXITCODE
} finally {
    Pop-Location
}
exit $code
