$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$venvPath = Join-Path $projectRoot '.venv'
if (-not (Test-Path $venvPath)) { python -m venv $venvPath }
$python = Join-Path $venvPath 'Scripts\python.exe'
$env:PYTHONUTF8 = '1'
& $python -m pip install --upgrade pip
& $python -m pip install -r (Join-Path $projectRoot 'requirements.txt')
$env:OFFLINE_MODE = 'true'
& $python -m uvicorn app:app --host 127.0.0.1 --port 8000
