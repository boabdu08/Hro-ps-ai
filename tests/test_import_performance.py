"""Import-performance regression tests.

Importing api / dashboard_sections must NOT pull heavy ML libraries
(tensorflow, shap, sklearn, scipy) at module-import time — they are lazy-loaded
inside the functions that need them. A regression here silently adds 15-30 s
to every API/dashboard cold start.

Each check runs in a subprocess so test ordering can't pollute sys.modules.
"""

import subprocess
import sys

import pytest

HEAVY_FORBIDDEN = ["tensorflow", "shap", "sklearn", "scipy"]


def _modules_after_import(module_name: str) -> set:
    code = (
        "import os, sys, json; "
        "os.environ.setdefault('APP_ENV', 'test'); "
        f"import {module_name}; "
        "roots = sorted({m.split('.')[0] for m in sys.modules}); "
        "print(json.dumps(roots))"
    )
    out = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, timeout=300
    )
    assert out.returncode == 0, f"import {module_name} failed:\n{out.stderr[-2000:]}"
    import json

    return set(json.loads(out.stdout.strip().splitlines()[-1]))


@pytest.fixture(scope="module")
def api_modules():
    return _modules_after_import("api")


@pytest.fixture(scope="module")
def dash_modules():
    return _modules_after_import("dashboard_sections")


class TestApiImportStaysLight:
    @pytest.mark.parametrize("heavy", HEAVY_FORBIDDEN)
    def test_api_does_not_import(self, api_modules, heavy):
        assert heavy not in api_modules, (
            f"`import api` eagerly pulled `{heavy}` — defer it into the "
            "function that needs it (see evaluation_service/resource_optimizer)."
        )


class TestDashboardImportStaysLight:
    @pytest.mark.parametrize("heavy", HEAVY_FORBIDDEN)
    def test_dashboard_sections_does_not_import(self, dash_modules, heavy):
        assert heavy not in dash_modules, (
            f"`import dashboard_sections` eagerly pulled `{heavy}` — defer it."
        )
