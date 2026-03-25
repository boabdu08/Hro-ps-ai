$ErrorActionPreference = 'Stop'

if (Test-Path .\venv\Scripts\python.exe) {
  $py = Resolve-Path .\venv\Scripts\python.exe
} elseif (Test-Path .\.venv311\Scripts\python.exe) {
  $py = Resolve-Path .\.venv311\Scripts\python.exe
} else {
  throw "No local venv python found. Create venv or .venv311 first."
}

Write-Host "Seeding DB from CSV (idempotent). Set SEED_FORCE=true to force re-seed." -ForegroundColor Cyan
& $py seed_from_csv.py
