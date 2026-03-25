# 🏥 AI Hospital Operations Dashboard

A **real-time hospital management system** powered by AI, Streamlit, and predictive analytics.  
Manage patient flow, optimize resources, and simulate hospital scenarios with AI.

---

## 🔹 Features

- **Hospital Control Panel** – Manage beds, doctors, and patient demand dynamically.
- **ER Emergency Simulator** – Simulate incoming emergency patients.
- **Live Patient Stream** – Real-time patient inflow simulation.
- **AI Resource Optimizer** – Auto-suggest doctors, nurses, and ICU beds.
- **ICU Risk Predictor** – Predict ICU load based on patient demand.
- **Smart Hospital Alerts** – Automatic alerts for bed and doctor shortages.
- **Digital Twin Visualization** – Overview of hospital occupancy and departments.
- **AI Patient Flow Predictor** – Forecast patient numbers hour-by-hour.

---

## 🔹 Technologies

- Python 3.13
- Streamlit
- TensorFlow / Keras
- Pandas, NumPy, Matplotlib
- SHAP (Model Explainability)
- GitHub (Version Control)

---

## 🔹 Setup Instructions

### 1) Clone the repository

```bash
git clone https://github.com/username/hro-ps-ai.git
cd hro-ps-ai
```

### 2) Recommended local run commands (Windows)

This repo historically ended up with **two venvs** in some environments (`venv/` and `.venv311/`).
To avoid interpreter mismatch issues (missing deps, different Python versions), use the PowerShell scripts below.
They auto-select `venv` first, then `.venv311`.

```powershell
./scripts/seed.ps1
./scripts/run_api.ps1
./scripts/run_dashboard.ps1

# optional always-on pipeline
./scripts/run_worker.ps1
```

> Note: If your PowerShell execution policy blocks running scripts, use:
> `powershell -ExecutionPolicy Bypass -Command "& ./scripts/run_dashboard.ps1"`
