param(
  [ValidateSet("dev", "test", "prod")][string]$Environment = "dev",
  [ValidateSet("memory", "postgres")][string]$Storage = "memory",
  [ValidateSet("memory", "redis")][string]$SessionStorage = "memory",
  [ValidateSet("mock", "ruoyi")][string]$Iam = "mock",
  [int]$Port = 8000
)

$ErrorActionPreference = "Stop"
$root = Split-Path $PSScriptRoot -Parent
$python = Join-Path $root "agent-server\.venv\Scripts\python.exe"
if (-not (Test-Path $python)) { $python = "python" }
$env:AGENT_APP_ENV = $Environment
$env:AGENT_STORAGE_MODE = $Storage
$env:AGENT_SESSION_STORAGE_MODE = $SessionStorage
$env:AGENT_IAM_MODE = $Iam
if ($Environment -eq "prod") { $env:AGENT_RUNTIME_EXECUTION_MODE = "disabled" }
Push-Location (Join-Path $root "agent-server")
try { & $python -m uvicorn app.main:app --host 0.0.0.0 --port $Port }
finally { Pop-Location }