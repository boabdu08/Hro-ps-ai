# HRO‑PS Dashboard — Fix & Enhancement Tasks

**Audience:** Claude Code, running locally in `D:\hro-ps-ai`.
**Goal:** Fix broken tabs, audit every tab, speed up the app, finish the dark‑mode pass, and make the Home tab interactive. **UI/bug/perf only — do not change forecasting/optimization logic, model weights, metrics, or the canonical `ForecastState` wiring.**

---

## 0. Setup & ground rules

**Run the app (two processes is the reliable dev mode):**
- API: `./scripts/run_api.ps1` (FastAPI in `main.py` / `api.py`, default `http://127.0.0.1:8000`).
- Dashboard: `./scripts/run_dashboard.ps1` (Streamlit `dashboard.py`). `app.py` is the single‑process HF Spaces entry; for debugging prefer the two scripts.
- Activate the repo venv first: `./venv/Scripts/Activate.ps1`.

**Find demo logins** for the three roles (admin, doctor, nurse) — check `scripts/seed_demo.py`, `users.csv`, `seed_from_csv.py`, `DEMO_RUNBOOK.md`. Re‑seed if the DB is empty (`python scripts/seed_demo.py`). If demo dates look stale, run `python scripts/refresh_demo_dates.py --db`.

**Reproduce before fixing.** For every "blank tab," log in as the relevant role, open the tab, and capture the **exact Streamlit traceback** (red box) and the **browser console** + the API process stdout. Fix the root cause, then re‑open the tab to confirm content renders.

**Don't break:**
- Model numbers / `ForecastState` / artifact wiring. Pure UI + bugfix + perf.
- The test suite. Run `python -m pytest -q` and `python scripts/smoke_forecast_state.py` before and after; keep all 277 green.

**Key files (already mapped):**
`dashboard.py` (router + roles + theme toggle + login), `ui_components.py` (design tokens, theme, CSS, `scoped_key`), `notification_sections.py`, `staff_sections.py` (appointments / OR / shifts), `home_section.py`, `dashboard_sections.py`, `message_center_sections.py`, `approval_sections.py`, `audit_sections.py`, `api_client.py`, `api.py`/`main.py`, `auth.py`, `.streamlit/config.toml`.

---

## Task 1 — Role tabs that render nothing

### 1a. Notifications — blank for **all** roles (admin, doctor, nurse)
Router: every role → `show_notifications_panel(user)` in `notification_sections.py`, which calls `show_alerts_center` → `show_notifications_center` → `_render_preferences`. A page header renders before any API call, so a truly blank page means an **exception** or a **hang**.

Prioritised hypotheses:
1. **Duplicate Streamlit element IDs (most likely).** Alert cards use `key=f"ack_{alert_id}"` / `f"resolve_{alert_id}"`; notification cards use `key=f"read_{notification_id}"`. If `alert_id` / `notification_id` is empty or duplicated in the data, keys collide → `StreamlitDuplicateElementId` → the whole tab dies. **Fix:** make every widget key unique (append an `enumerate()` index, e.g. `f"ack_{idx}_{alert_id}"`), in `_render_alert_card`, `_render_notification_card`, and the filter selectboxes.
2. **API failure/slow path.** `/alerts`, `/notifications`, `/notifications/unread_count`, `/notifications/preferences` may 401/500 or be slow (each call has a 10–15 s timeout; several run sequentially). Confirm against the API stdout. Make the panel resilient: if a call returns `None`, show a clear inline message instead of letting downstream code throw.
3. **Exception inside `st.tabs` / DataFrame sort** in `show_notifications_center` (`pd.DataFrame(rows)`, `sort_values("created_at")`). Guard for missing columns / non‑dict rows.

Deliver: Notifications renders for all three roles, with real data when the API is up and a graceful empty/error state when it isn't.

### 1b. Doctor — Appointments **and** OR Bookings blank (admin/nurse appointments work)
Root cause (high confidence): exact string‑equality filter on the doctor's display name.
- `dashboard.py`: doctor routes call `show_appointments("doctor", doctor_name=user.get("name"))` and `show_or_bookings("doctor", doctor_name=user.get("name"))`.
- `staff_sections.py`: `df = df[df["doctor"] == doctor_name]`. If the seeded `Appointment.doctor` / `ORBooking.doctor` value doesn't **exactly** equal the logged‑in user's `name` (case, "Dr." prefix, username vs full name), the filter empties the frame → "No appointments available." Admin is unfiltered, so it works.

**Fix options (pick the robust one, verify with real seed data):**
- Normalise both sides and match case‑insensitively / by contains, e.g. compare `.str.strip().str.casefold()`; strip a leading `dr.`; optionally also match on `user["username"]`.
- And/or align the seed data so `doctor` matches the user identity.
- Add a tiny diagnostic when the unfiltered frame is non‑empty but the filtered one is empty ("No records matched *Dr. X* — showing department view / check naming").

Also re‑verify **nurse** Appointments (`department=` filter) and **admin** `show_admin_appointments_overview()` still populate.

---

## Task 2 — Audit every tab, every role

Open each route and fix any error/blank. Full route map from `dashboard.py`:

- **Admin:** Home · Command Center · Forecast · Optimization · Operations Center (Operations / Simulation / Digital Twin / Department Status sub‑tabs) · Shifts · Appointments · OR Bookings · Notifications · Messages · Approvals · Evaluation · Explainability · Audit.
- **Doctor:** Home · Overview · Forecast · My Shifts · Appointments · OR Bookings · Notifications · Messages.
- **Nurse:** Home · Overview · My Shifts · Appointments · Department · Notifications · Messages.

For each: confirm it renders, no traceback, no duplicate‑key error, charts/tables show data (or a clean empty state when the API/DB is down). Pay attention to `st.button`/`st.plotly_chart`/`st.dataframe` keys built from possibly‑empty values (same duplicate‑key risk as Task 1). Note `Approvals` depends on a live forecast context (`get_live_context()`); make its failure mode explicit rather than blank.

---

## Task 3 — Performance: slow login, slow tab switching, slow theme toggle

### Theme toggle (worst offender)
In `dashboard.py`: toggling calls `set_theme_mode()` → `_set_query_params(theme=…)` → `st.rerun()`, and `_sync_theme_local_storage()` injects JS that can call `root.location.replace(url)` — a **full browser reload**. That's why switching dark/light is slow.
- Remove the forced `location.replace` reload from the theme path (keep at most a one‑time bootstrap, not on every toggle).
- Prefer a **CSS‑only switch**: inject both light and dark token sets and flip a `data-hro-theme` attribute on `<html>` (no Python `st.rerun()` needed). If keeping the Python rerun, at least drop the JS reload and the query‑param round‑trip.

### Per‑rerun overhead (slow tab switches)
Every rerun injects **three `components.html` iframes** (`_sync_theme_local_storage`, `_inject_dynamic_import_recovery`, `inject_page_context`) **plus** the large `<style>` block from `inject_base_styles()`. Each iframe is real DOM weight on every navigation.
- Inject the big stylesheet and the import‑recovery script **once per session** (guard with a `st.session_state` flag).
- Only re‑emit `inject_page_context` / theme sync when the page or theme actually changes.

### Login
`app.py` `_ensure_api_running()` blocks up to ~30 s for API cold start, and the first `/predict` lazy‑loads TensorFlow (`get_prediction` timeout is 90 s). After login, the sidebar/home immediately call `get_live_context()`.
- Check the **bcrypt cost factor** in `auth.py` (`/auth/login`) — high rounds make every login slow; pick a sane factor.
- Show a determinate spinner during cold start; pre‑warm the model in the API startup (without training) so the first `/predict` isn't a 10–30 s stall.
- Keep `get_live_context()` cached (it already is, TTL 20 s) and make sure login itself doesn't trigger a heavy `/predict` synchronously.

Measure before/after (rough wall‑clock for login, tab switch, theme flip) and note the numbers.

---

## Task 4 — Dark‑mode resolution / completeness

Two concrete root causes:

1. **`.streamlit/config.toml` hard‑codes a LIGHT base theme** (`backgroundColor=#F7F9FB`, `secondaryBackgroundColor=#FFFFFF`, `textColor=#1F2937`). Streamlit/BaseWeb render overlays in a portal at the document root that the app's scoped CSS doesn't fully reach, so in "dark mode" these stay light: **selectbox/multiselect dropdown menus, date pickers, tooltips, `st.metric`, expanders, code blocks, `st.toast`, sliders, file uploader, dataframe header/cells/scrollbars**. Fix by theming these explicitly for dark mode (target the BaseWeb portal/popover classes and `[data-testid="stMetric"]`, `[data-testid="stExpander"]`, etc.) and/or reconciling the base theme so native widgets aren't stuck light.
2. **Python theme vs JS attribute mismatch.** CSS variables come from Python `get_theme_mode()`, but the Command‑Center dark overrides key off `html[data-hro-theme="dark"]`, which `inject_page_context` sets **only from `localStorage`**. On first load / right after a toggle these can disagree → half‑dark UI. Make `data-hro-theme` always reflect the current Python theme (pass it in, don't rely solely on localStorage).

Deliver a dark‑mode audit pass over every tab: no white cards/menus/popovers, readable text/contrast everywhere, Plotly charts transparent (already partly handled), tables and KPI cards consistent. Keep the existing token palette.

---

## Task 5 — Interactive Home tab (click → navigate)

`home_section.py` currently shows non‑clickable `kpi_card` HTML, charts, and compact `st.dataframe` tables (Dept Status, Upcoming Appointments, OR Bookings). Make the Home tab a launchpad:
- **Buttons jump to their tab** (e.g. a "Forecast →" action opens Forecast; "Appointments →" opens Appointments; Active‑Alerts → Notifications; etc.).
- **Clicking a compact table opens its full tab** (e.g. the Appointments snapshot → Appointments page).

**Navigation mechanism (important Streamlit detail):** the sidebar nav is `st.sidebar.radio(..., key=scoped_key("sidebar","navigation",role))` in `dashboard.py`. To drive it from Home:
- Use an **`on_click` callback** that sets the target page (callbacks run before widgets are instantiated, so this avoids `StreamlitAPIException: <key> cannot be modified after the widget is instantiated`). Either set the radio's own key, or set a separate `st.session_state["nav_target"]` and have `sidebar_navigation()` consume it (compute `index=pages.index(target)`, then clear it).
- `show_home()` will need the `role` (and/or the nav key) — pass it from `main_app()`.
- Do **not** set the radio key inline in the same run after the radio was already created — that throws. Use the callback/`nav_target` pattern.

**Clickable tables:** Streamlit is `>=1.54`, so `st.dataframe(..., on_select="rerun", selection_mode="single-row")` is available — on selection, navigate to the relevant tab. If row‑selection UX is fiddly, fall back to a clear **"Open full view →" button** beside each compact table. A per‑section button is the robust baseline; add row‑click on top if it tests cleanly.

Keep the current premium look (reuse `kpi_card`, section headers, tokens). Buttons should be obvious but not noisy.

---

## Acceptance criteria

- [ ] Notifications renders for admin, doctor, nurse (data when API up; clean empty/error state when down).
- [ ] Doctor sees their own Appointments **and** OR Bookings; admin overview and nurse appointments still work.
- [ ] Every tab for every role renders with no traceback and no duplicate‑key error.
- [ ] Theme toggle is near‑instant with **no full page reload**; tab switches feel snappy.
- [ ] Login is faster / shows clear progress; bcrypt cost sane; no synchronous heavy predict on login.
- [ ] Dark mode: no light dropdowns/menus/cards; consistent contrast across all tabs.
- [ ] Home buttons and tables navigate to the correct tab for all three roles.
- [ ] `python -m pytest -q` all green; `python scripts/smoke_forecast_state.py` passes; model metrics / `ForecastState` unchanged.

## Suggested order
1 (fix blanks) → 2 (audit all) → 4 (dark mode) → 3 (perf) → 5 (home interactivity). Commit per task with a short message; summarise the root cause and fix for each in your final report.
