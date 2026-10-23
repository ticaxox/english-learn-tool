[CmdletBinding()]
param(
    [string]$RunId = 'm3-scheduler-run1',
    [string]$RuntimeEnv = 'E:\agent workspace\英语学习工具\ai-workspace\10-collaboration\sessions\A30-TEST\temp\m3ai-runtime\runtime.env',
    [string]$EvidenceDir = 'E:\agent workspace\英语学习工具\ai-workspace\04-qa\evidence\T-QA-002',
    [string]$RepoRoot = 'E:\agent workspace\英语学习工具\worktrees\A30-TEST'
)
$ErrorActionPreference = 'Stop'
$settings = @{}
foreach ($line in Get-Content -LiteralPath $RuntimeEnv) { if ($line -match '^([A-Z0-9_]+)=(.*)$') { $settings[$Matches[1]] = $Matches[2] } }
$dbUrl = $settings['DATABASE_URL'] -replace '^postgresql\+asyncpg://', 'postgresql://' -replace '@postgres:5432/', '@127.0.0.1:55444/'
$env:PYTHONIOENCODING = 'utf-8'
$env:PYTHONPATH = Join-Path $RepoRoot 'backend'
$env:LIVE_API_BASE_URL = 'http://127.0.0.1:8092'
$env:LIVE_PG_DSN = $dbUrl
$env:LIVE_REDIS_URL = 'redis://127.0.0.1:55445/0'
$env:LIVE_PROVIDER_CONTROL_URL = 'http://127.0.0.1:18081'
$env:EVIDENCE_DIR = $EvidenceDir
$env:LIVE_RUN_ID = $RunId
$env:LIVE_ADMIN_USERNAME = 'qa_m3_ai_admin'
$env:LIVE_ADMIN_PASSWORD = $settings['QA_BOOTSTRAP_ADMIN_PASSWORD']
$env:RUNTIME_ENV = $RuntimeEnv
$env:REPO_ROOT = $RepoRoot
$python = Join-Path $RepoRoot 'backend\.venv\Scripts\python.exe'
$runner = Join-Path $RepoRoot 'tests\m3-ai-int\m3_notification_scheduler.py'
Push-Location $RepoRoot
try { & $python $runner 2>&1; $code = $LASTEXITCODE } finally { Pop-Location }
exit $code
