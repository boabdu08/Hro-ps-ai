# One-command demo launcher: starts the API in the background, waits for
# /health, then starts the dashboard in the foreground.
#   powershell -ExecutionPolicy Bypass -File .\scripts\run_all.ps1
$ErrorActionPreference = 'Stop'

$repo = Split-Path -Parent $PSScriptRoot
Set-Location $repo

# Canonical environment: the repo venv (Python 3.13). See README quickstart.
$py = Join-Path $repo 'venv\Scripts\python.exe'
if (-not (Test-Path $py)) {
  throw "venv\Scripts\python.exe not found. Create it: python -m venv venv; venv\Scripts\pip install -r requirements.txt"
}

# 1) API in the background (skip if something already answers on :8000)
$apiUp = $false
try {
  Invoke-WebRequest -Uri 'http://127.0.0.1:8000/health' -TimeoutSec 2 -UseBasicParsing | Out-Null
  $apiUp = $true
  Write-Host '[run_all] API already running on :8000 - reusing it.'
} catch {}

if (-not $apiUp) {
  Write-Host '[run_all] Starting API (uvicorn main:app on :8000)...'
  Start-Process -FilePath $py -ArgumentList '-m','uvicorn','main:app','--port','8000' -WindowStyle Minimized
  $deadline = (Get-Date).AddSeconds(90)
  while ((Get-Date) -lt $deadline) {
    try {
      Invoke-WebRequest -Uri 'http://127.0.0.1:8000/health' -TimeoutSec 2 -UseBasicParsing | Out-Null
      $apiUp = $true
      break
    } catch { Start-Sleep -Milliseconds 500 }
  }
  if (-not $apiUp) { throw 'API did not answer /health within 90 s - check the uvicorn window.' }
  Write-Host '[run_all] API is up.'
}

# 2) Dashboard in the foreground (Ctrl+C stops it; API window keeps running)
Write-Host '[run_all] Starting dashboard (streamlit on :8501)...'
& $py -m streamlit run dashboard.py
