$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath (Split-Path -Parent $PSScriptRoot)
docker compose --profile checks build checks
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
docker compose --profile checks run --rm checks
exit $LASTEXITCODE
