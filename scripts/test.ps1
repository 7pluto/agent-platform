$ErrorActionPreference = "Stop"
$root = Split-Path $PSScriptRoot -Parent
Push-Location $root
try {
  ruff check agent-server/app agent-server/tests agent-server/migrations
  pytest -q agent-server/tests -p no:cacheprovider
  Push-Location agent-server
  try { alembic upgrade head --sql | Out-Null }
  finally { Pop-Location }
  Push-Location agent-console
  try { npm run build }
  finally { Pop-Location }
}
finally { Pop-Location }