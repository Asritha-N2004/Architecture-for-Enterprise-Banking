$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
$env:PYTHONPATH = Join-Path (Get-Location) 'backend'
if (-not $env:DEMO_PASSWORD) { throw 'Set DEMO_PASSWORD to a private demonstration password of at least 12 characters' }
& .\.venv\Scripts\python.exe -m app.seed
if ($LASTEXITCODE -ne 0) { throw 'Seed failed' }
