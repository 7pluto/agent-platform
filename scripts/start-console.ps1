param([int]$Port = 5173)
$ErrorActionPreference = "Stop"
$root = Split-Path $PSScriptRoot -Parent
Push-Location (Join-Path $root "agent-console")
try { npm run dev -- --host 0.0.0.0 --port $Port }
finally { Pop-Location }