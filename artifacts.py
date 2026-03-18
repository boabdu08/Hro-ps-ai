from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional


@dataclass(frozen=True)
class ArtifactPaths:
    base_dir: Path
    lstm_model: Path
    arimax_model: Path
    x_scaler: Path
    y_scaler: Path
    hybrid_config: Path
    manifest: Optional[Path] = None


def get_artifact_base_dir() -> Path:
    raw = (os.getenv("ARTIFACT_DIR") or ".").strip()
    return Path(raw).resolve()


def get_artifact_paths() -> ArtifactPaths:
    base = get_artifact_base_dir()
    manifest = base / "artifact_manifest.json"
    return ArtifactPaths(
        base_dir=base,
        lstm_model=base / "hospital_forecast_model.keras",
        arimax_model=base / "arimax_model.pkl",
        x_scaler=base / "x_scaler.pkl",
        y_scaler=base / "y_scaler.pkl",
        hybrid_config=base / "hybrid_config.json",
        manifest=manifest if manifest.exists() else None,
    )


def load_manifest() -> Dict[str, Any]:
    paths = get_artifact_paths()
    if not paths.manifest:
        return {}
    try:
        return json.loads(paths.manifest.read_text(encoding="utf-8"))
    except Exception:
        return {}


def artifact_diagnostics() -> Dict[str, Any]:
    paths = get_artifact_paths()
    required = {
        "hospital_forecast_model.keras": paths.lstm_model,
        "arimax_model.pkl": paths.arimax_model,
        "x_scaler.pkl": paths.x_scaler,
        "y_scaler.pkl": paths.y_scaler,
        "hybrid_config.json": paths.hybrid_config,
    }
    missing = [name for name, p in required.items() if not p.exists()]
    return {
        "artifact_dir": str(paths.base_dir),
        "missing": missing,
        "manifest": load_manifest(),
    }

