$ErrorActionPreference = 'Stop'
Set-Location (Join-Path $PSScriptRoot '..')
uv sync --project backend --locked --python 3.12
if ($LASTEXITCODE -ne 0) { throw 'Python dependency install failed' }
npm --prefix frontend ci
if ($LASTEXITCODE -ne 0) { throw 'Frontend dependency install failed' }
npm --prefix extension ci
if ($LASTEXITCODE -ne 0) { throw 'Extension dependency install failed' }
$api = Start-Process -FilePath 'uv' -ArgumentList @('run','--project','backend','--no-sync','uvicorn','app.main:create_app','--factory','--app-dir','backend','--host','127.0.0.1','--port','8000') -PassThru -NoNewWindow
try { npm --prefix frontend run dev } finally { if (!$api.HasExited) { Stop-Process -Id $api.Id } }
