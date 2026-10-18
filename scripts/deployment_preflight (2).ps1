$ErrorActionPreference = 'Stop'
python scripts/deployment_preflight.py @args
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
