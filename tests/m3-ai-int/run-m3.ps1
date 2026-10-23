<#
.SYNOPSIS
    Runs the one-shot T-QA-002 M3 API + browser acceptance chain.
#>
[CmdletBinding()]
param(
    [string]$RunId = 'm3-run1',
    [string]$RuntimeEnv = 'E:\agent workspace\英语学习工具\ai-workspace\10-collaboration\sessions\A30-TEST\temp\m3ai-runtime\runtime.env',
    [string]$EvidenceDir = 'E:\agent workspace\英语学习工具\ai-workspace\04-qa\evidence\T-QA-002',
    [string]$RepoRoot = 'E:\agent workspace\英语学习工具\worktrees\A30-TEST'
)
$ErrorActionPreference = 'Stop'
if (-not (Test-Path -LiteralPath $RuntimeEnv)) { throw "Missing runtime env file: $RuntimeEnv" }
$settings = @{}
foreach ($line in Get-Content -LiteralPath $RuntimeEnv) { if ($line -match '^([A-Z0-9_]+)=(.*)$') { $settings[$Matches[1]] = $Matches[2] } }
$dbUrl = $settings['DATABASE_URL'] -replace '^postgresql\+asyncpg://', 'postgresql://' -replace '@postgres:5432/', '@127.0.0.1:55444/'
$env:PYTHONIOENCODING = 'utf-8'
$env:PYTHONPATH = Join-Path $RepoRoot 'backend'
$env:LIVE_API_BASE_URL = 'http://127.0.0.1:8092'
$env:LIVE_WEB_BASE_URL = 'http://127.0.0.1:8093'
$env:LIVE_PG_DSN = $dbUrl
$env:LIVE_REDIS_URL = 'redis://127.0.0.1:55445/0'
$env:LIVE_PROVIDER_CONTROL_URL = 'http://127.0.0.1:18081'
$env:LIVE_PROVIDER_BASE_URL = 'http://a30-m3-ai-provider:18080/v1'
$env:EVIDENCE_DIR = $EvidenceDir
$env:LIVE_RUN_ID = $RunId
$env:LIVE_ADMIN_USERNAME = 'qa_m3_ai_admin'
$env:LIVE_ADMIN_PASSWORD = $settings['QA_BOOTSTRAP_ADMIN_PASSWORD']
$env:RUNTIME_ENV = $RuntimeEnv
$env:REPO_ROOT = $RepoRoot
$env:LIVE_PLAYWRIGHT_MODULE = 'E:\agent workspace\英语学习工具\ai-workspace\10-collaboration\sessions\A20-VIEW\temp\a20-browser-check\node_modules\playwright-core\index.mjs'
$env:LIVE_BROWSER_EXECUTABLE = 'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe'
$python = Join-Path $RepoRoot 'backend\.venv\Scripts\python.exe'
$runner = Join-Path $RepoRoot 'tests\m3-ai-int\m3_api.py'
$log = Join-Path $EvidenceDir "logs\$RunId.log"
New-Item -ItemType Directory -Force -Path (Split-Path -Parent $log) | Out-Null
Push-Location $RepoRoot
try {
    & $python $runner 2>&1 | Tee-Object -FilePath $log
    $code = $LASTEXITCODE
} finally {
    Pop-Location
}
exit $code
