# DEPLOY_HF_SPACE — exact steps to put HRO-PS on a Hugging Face Space

Pre-flight status (run `python scripts/preflight_hf_space.py` to re-verify): **ALL PASS** —
streamlit serves, app.py first-session boot starts the internal API, `admin1/123456` login
works on the SQLite fallback, `/forecast_state` returns 72 forecast values.

> **Why a special push is needed:** two git-tracked files exceed HF's 10 MB plain-git limit
> (`artifacts/models_72h/arimax_ops72h.pkl` 53.5 MB, `arimax_model.pkl` 27.6 MB). HF requires
> Git LFS for them. `.gitattributes` (already committed) covers NEW objects, but both files
> already exist in normal git history — so pushing `origin/main`'s history to the Space will be
> **rejected**. Use the single-commit snapshot push below. **Never rewrite `origin/main`.**

## 0. One-time prerequisites (your machine)

```powershell
git lfs version    # already installed: git-lfs/3.7.1 — else: winget install Git.GitLFS
git lfs install    # enables LFS hooks for your user (safe to re-run)
```

## 1. Create the Space (browser)

1. https://huggingface.co/new-space → Owner: your account · Space name: `hro-ps-ai`
2. SDK: **Streamlit** · Hardware: free CPU basic is fine · Visibility: your choice.
3. Do NOT initialise with files.

## 2. Set the Space secret (browser)

Space → Settings → Variables and secrets → **New secret**:
- Name: `JWT_SECRET_KEY` · Value: a long random string (e.g. output of
  `python -c "import secrets; print(secrets.token_urlsafe(48))"`)

(`DATABASE_URL` is optional — without it the Space uses a local SQLite demo DB, which the
pre-flight validated end-to-end. `APP_ENV` defaults to `dev`, which auto-seeds demo users.)

## 3. Authenticate (requires YOUR HF login — run yourself)

```powershell
pip install -U huggingface_hub
hf auth login          # paste a WRITE token from https://huggingface.co/settings/tokens
```

## 4. Snapshot push (RECOMMENDED — fresh single commit, origin untouched)

Run from `D:\hro-ps-ai` (replace `<USER>`):

```powershell
# 4.1 a clean snapshot branch with NO history (orphan)
git checkout --orphan hf-space-snapshot
git add -A

# 4.2 make the Space README the snapshot's README (Space card YAML lives there)
Copy-Item README_HF_SPACE.md README.md -Force
git add README.md

# 4.3 convert the >10 MB files (and all .gitattributes-matched binaries) to LFS
git lfs track            # confirm patterns from .gitattributes are active
git rm --cached arimax_model.pkl artifacts/models_72h/arimax_ops72h.pkl
git add arimax_model.pkl artifacts/models_72h/arimax_ops72h.pkl   # re-added as LFS now

git commit -m "HRO-PS demo Space snapshot"

# 4.4 push the snapshot to the Space as its main branch
git remote add space https://huggingface.co/spaces/<USER>/hro-ps-ai
git push --force space hf-space-snapshot:main

# 4.5 return to your normal branch (origin history untouched)
git checkout main
```

### Alternative (NOT recommended): `git lfs migrate import` on a separate clone
Only if you want full history on the Space: make a **fresh clone elsewhere**, run
`git lfs migrate import --include="*.pkl" --everything` **in that clone only**, then push that
clone to the `space` remote. This rewrites the clone's history — which is why it must never
be done in this working repo or pushed to `origin`.

## 5. First boot — what to expect

| Moment | Expected |
|---|---|
| Build | ~5–10 min (23 wheels incl. TensorFlow; all pins verified cp311/manylinux — no source builds) |
| First page load | Streamlit UI in a few seconds; internal API boots on the first session (~10 s; pre-flight measured 10 s total to a working login) |
| Login | `admin1` / `123456` (auto-seeded in dev mode) |
| First Explainability / live predict | **~30 s one-time TF model load** — the UI says so; later calls are fast |
| Forecasts | Pre-generated artifacts (no training on startup, ever) |

## 6. Verification checklist (after the Space turns green)

- [ ] Page loads; login `admin1/123456` succeeds
- [ ] Sidebar System Status: online (no "API not reachable" banner)
- [ ] Home shows KPIs incl. Appts (7-day) > 0
- [ ] Forecast tab renders the 72-h chart with the uncertainty band
- [ ] Evaluation tab shows the canonical metrics table (LSTM 7.65/9.58/5.52 etc.)
- [ ] Explainability returns after the one-time model warm-up

Troubleshooting: Space → Logs. The three usual suspects are a missing `JWT_SECRET_KEY`
secret, a file rejected for size (means the LFS step 4.3 was skipped), or a stale
`README.md` without the Space-card YAML header (step 4.2).
