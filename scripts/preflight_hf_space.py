"""Hugging Face Space cold-boot simulation (run BEFORE creating the Space).

Mimics a brand-new Space container locally:
* sanitized env — fresh temp sqlite DATABASE_URL, dummy JWT_SECRET_KEY,
  no API_TOKEN, APP_ENV=dev (so demo users self-seed)
* launches `streamlit run app.py` headless (the Space's exact entrypoint)
* asserts, within a 120 s budget:
    1. dashboard serves HTTP 200
    2. internal FastAPI /health answers ok
    3. POST /auth/login admin1/123456 succeeds (dev seeding worked)
    4. GET /forecast_state returns forecast data (artifacts load)
* clean teardown — no orphaned processes on the test ports.

Usage:  python scripts/preflight_hf_space.py
Exit code 0 = all steps PASS.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import requests

REPO_ROOT = Path(__file__).resolve().parent.parent
DASH_PORT = int(os.getenv("PREFLIGHT_DASH_PORT", "8511"))
API_PORT = int(os.getenv("PREFLIGHT_API_PORT", "7871"))
BUDGET_S = 120


def _step(name: str, ok: bool, detail: str = "") -> bool:
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f" — {detail}" if detail else ""))
    return ok


def main() -> int:
    tmpdir = tempfile.mkdtemp(prefix="hf_preflight_")
    env = dict(os.environ)
    # Sanitized container-like env (explicitly OVERRIDE, not setdefault).
    env.update(
        {
            "APP_ENV": "dev",
            "DATABASE_URL": f"sqlite:///{Path(tmpdir).as_posix()}/space_demo.db",
            "JWT_SECRET_KEY": "preflight-dummy-secret-not-for-production",
            "API_BASE_URL": f"http://127.0.0.1:{API_PORT}",
            "INTERNAL_API_PORT": str(API_PORT),
        }
    )
    env.pop("API_TOKEN", None)

    print(f"HF Space pre-flight (dash :{DASH_PORT}, api :{API_PORT}, db {tmpdir})")
    t0 = time.time()
    results: list[bool] = []

    # ------------------------------------------------------------------
    # Step 0 — Python 3.11 syntax sweep. The Space runtime is 3.11 while local
    # dev is 3.13; 3.12+-only syntax (e.g. nested same-quote f-strings) would
    # crash the Space at boot. Skipped (with a warning) if no 3.11 available.
    # ------------------------------------------------------------------
    import shutil as _shutil

    py311 = (
        os.getenv("PYTHON311")
        or (r"C:\Users\Ab005\AppData\Local\Programs\Python\Python311\python.exe"
            if os.name == "nt" else "")
        or _shutil.which("python3.11")
        or ""
    )
    if py311 and Path(py311).exists():
        runtime_modules = [
            str(p.name) for p in REPO_ROOT.glob("*.py")
            if not p.name.startswith(("test", "tmp_", "train_", "build_", "make_",
                                      "inspect_", "scan_", "update_", "insert_",
                                      "remap_", "gen_", "generate_", "experiment_",
                                      "seed_", "verify_", "validate_", "canonical_"))
        ]
        out = subprocess.run(
            [py311, "-m", "compileall", "-q", *runtime_modules],
            cwd=str(REPO_ROOT), capture_output=True, text=True, timeout=300,
        )
        results.append(_step("python 3.11 syntax sweep", out.returncode == 0,
                             (out.stderr or out.stdout)[:200].strip()))
    else:
        print("  SKIP  python 3.11 syntax sweep (no 3.11 interpreter found; set PYTHON311)")

    # ------------------------------------------------------------------
    # Step 1 — the Streamlit SERVER serves HTTP 200 with app.py as entrypoint
    # (what HF's health check sees). NOTE: a plain GET does NOT execute the
    # script — Streamlit runs app code only when a browser session connects.
    # ------------------------------------------------------------------
    proc = subprocess.Popen(
        [sys.executable, "-m", "streamlit", "run", "app.py",
         "--server.headless", "true", "--server.port", str(DASH_PORT)],
        cwd=str(REPO_ROOT), env=env,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    try:
        ok, detail = False, ""
        while time.time() - t0 < 60:
            try:
                r = requests.get(f"http://127.0.0.1:{DASH_PORT}", timeout=2)
                if r.status_code == 200:
                    ok, detail = True, f"{time.time()-t0:.0f}s"
                    break
            except requests.RequestException:
                time.sleep(1)
        results.append(_step("streamlit server (app.py) HTTP 200", ok, detail))
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=15)
        except subprocess.TimeoutExpired:
            proc.kill()

    # ------------------------------------------------------------------
    # Steps 2-4 — simulate the FIRST BROWSER SESSION: execute app.py the way
    # Streamlit does (AppTest script run). This triggers app.main() →
    # _ensure_api_running() → internal uvicorn → dashboard render, exactly
    # the cold-boot path a real visitor causes on the Space.
    # ------------------------------------------------------------------
    os.environ.update(env)  # sanitized env for the in-process run
    os.environ["STREAMLIT_SERVER_PORT"] = str(DASH_PORT)  # satisfies app.py's run guard

    ok, detail = False, ""
    try:
        from streamlit.testing.v1 import AppTest

        at = AppTest.from_file(str(REPO_ROOT / "app.py"), default_timeout=BUDGET_S)
        at.run()
        exc = list(at.exception)
        ok = not exc
        detail = f"{time.time()-t0:.0f}s" if ok else str(exc[0].value)[:150]
    except Exception as e:
        detail = str(e)[:150]
    results.append(_step("app.py script run (first session) clean", ok, detail))

    base = f"http://127.0.0.1:{API_PORT}"
    ok, detail = False, ""
    deadline = time.time() + 60
    while time.time() < deadline:
        try:
            r = requests.get(f"{base}/health", timeout=2)
            if r.ok and r.json().get("status") == "ok":
                ok, detail = True, f"{time.time()-t0:.0f}s"
                break
        except requests.RequestException:
            time.sleep(1)
    results.append(_step("internal API /health ok", ok, detail))

    token = None
    ok, detail = False, ""
    if results[-1]:
        try:
            r = requests.post(
                f"{base}/auth/login",
                json={"username": "admin1", "password": "123456", "tenant": "demo-hospital"},
                timeout=30,
            )
            if r.ok and r.json().get("access_token"):
                token = r.json()["access_token"]
                ok, detail = True, f"{time.time()-t0:.0f}s"
            else:
                detail = f"HTTP {r.status_code}: {r.text[:120]}"
        except requests.RequestException as e:
            detail = str(e)[:120]
    results.append(_step("auth/login admin1 succeeds (dev seeding)", ok, detail))

    ok, detail = False, ""
    if token:
        try:
            r = requests.get(
                f"{base}/forecast_state",
                headers={"Authorization": f"Bearer {token}"}, timeout=60,
            )
            payload = r.json() if r.ok else {}
            vals = (payload.get("forecast_state") or payload).get("forecast_72h_values") or []
            ok = r.ok and len(vals) >= 24
            detail = f"{len(vals)} forecast values" if ok else f"HTTP {r.status_code}: {r.text[:120]}"
        except Exception as e:
            detail = str(e)[:120]
    results.append(_step("/forecast_state returns 72h data", ok, detail))

    all_ok = all(results)
    print(f"\nPre-flight: {'ALL PASS' if all_ok else 'FAILURES — fix before creating the Space'} "
          f"({time.time()-t0:.0f}s total)")
    # The in-process uvicorn thread is a daemon: it dies with this process,
    # so the API port is freed on exit (no orphan teardown needed).
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
