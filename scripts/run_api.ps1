$ErrorActionPreference = 'Stop'

if (Test-Path .\venv\Scripts\python.exe) {
  $py = Resolve-Path .\venv\Scripts\python.exe
} elseif (Test-Path .\.venv311\Scripts\python.exe) {
  $py = Resolve-Path .\.venv311\Scripts\python.exe
} else {
  throw "No local venv python found. Create venv or .venv311 first."
}

& $py -m uvicorn api:app --reload
