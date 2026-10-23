<#
.SYNOPSIS
    Runs the one-shot M2-CORE-INT-001 Phase B API + browser acceptance chain.
#>
[CmdletBinding()]
param(
    [string]$RunId = 'phase-b-run1',
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
$env:LIVE_WEB_BASE_URL = 'http://127.0.0.1:8091'
$env:LIVE_PG_DSN = $dbUrl
$env:EVIDENCE_DIR = $EvidenceDir
$env:LIVE_RUN_ID = $RunId
$env:LIVE_ADMIN_USERNAME = 'qa_m2core_admin'
$env:LIVE_ADMIN_PASSWORD = $settings['QA_BOOTSTRAP_ADMIN_PASSWORD']
$env:RUNTIME_ENV = $RuntimeEnv
$env:REPO_ROOT = $RepoRoot
$env:LIVE_PLAYWRIGHT_MODULE = 'E:\agent workspace\英语学习工具\ai-workspace\10-collaboration\sessions\A20-VIEW\temp\a20-browser-check\node_modules\playwright-core\index.mjs'
$env:LIVE_BROWSER_EXECUTABLE = 'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe'

$python = Join-Path $RepoRoot 'backend\.venv\Scripts\python.exe'
$runner = Join-Path $RepoRoot 'tests\m2-core-int\phase_b_api.py'
$log = Join-Path $EvidenceDir "phase-b\logs\$RunId.log"
$logDir = Split-Path -Parent $log
New-Item -ItemType Directory -Force -Path $logDir | Out-Null

Push-Location $RepoRoot
try {
    & $python $runner 2>&1 | Tee-Object -FilePath $log
    $code = $LASTEXITCODE
} finally {
    Pop-Location
}
exit $code
