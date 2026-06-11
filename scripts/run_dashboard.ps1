$ErrorActionPreference = 'Stop'

# Canonical environment: the repo venv (Python 3.13) - the ONLY supported env.
# (.venv / .venv311 were removed in the perf consolidation pass.)
$repo = Split-Path -Parent $PSScriptRoot
$py = Join-Path $repo 'venv\Scripts\python.exe'
if (-not (Test-Path $py)) {
  throw "venv\Scripts\python.exe not found. Create it: python -m venv venv; venv\Scripts\pip install -r requirements.txt"
}

& $py -m streamlit run dashboard.py
