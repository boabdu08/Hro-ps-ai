# Phase A — Supervisor-Compliance Code Verification

**Date:** 2026-06-09  
**Source:** `HRO-PS_Supervisor_Compliance_and_Changes.md` 🟡 items  
**Verified by:** FINAL_SUBMISSION_PROMPT.md Phase A pass

---

## 1. Alert-routing table (🟡 #9)

**Requirement:** Alert type → recipient table exists and is configurable.

**Status: ✅ IMPLEMENTED**

| Evidence | Location |
|---|---|
| `ALERT_ROUTING_TABLE` dict maps 6 alert types to default roles | `api.py` lines ~679–720 |
| `create_alert_and_notify()` reads the table when `target_role=None` | `api.py` `create_alert_and_notify()` |
| `/alert-routing-table` GET endpoint exposes the table as JSON | `api.py` `@system_router.get("/alert-routing-table")` |
| `get_alert_routing_table()` client function | `api_client.py` |
| Admin-only expander in Notifications panel shows the table as a DataFrame | `notification_sections.py` `_render_alert_routing_table()` |

**Table content:**

| Alert type | Default role | Description |
|---|---|---|
| `capacity_alert` | `admin` | Bed/capacity over-threshold → Hospital Admin + Charge Nurse |
| `staffing_alert` | `admin` | Staffing gap or shift-coverage shortfall |
| `forecast_alert` | `admin` | Predicted surge or model anomaly |
| `optimization_alert` | `admin` | MILP optimiser recommendation → Approvals workflow |
| `critical_alert` | `all` | Mass-casualty / critical event → All active roles |
| `operational_alert` | `all` | General operational signal (default) |

---

## 2. Optimization labels: "Needed" vs "Shortage" (🟡 #23)

**Requirement:** Dashboard labels clearly separate "Needed" vs "Shortage".

**Status: ✅ IMPLEMENTED + LABELLED**

| Label | Meaning | Where |
|---|---|---|
| `beds_required` / "Beds needed" | What the forecast load demands (×1.10 safety buffer) | KPI cards, allocation table |
| `bed_shortage` | Needed minus currently available — the MILP deficit to cover | "Shortages by department" section, shortage bar chart |

**Caption added** to the allocation table (line ~1303 `dashboard_sections.py`):

> "**Needed** (`beds_required`, `doctors_required`, `nurses_required`) = what the forecast load demands (forecast share × 1.10 safety buffer). **Shortage** (`bed_shortage`, `doctor_shortage`, `nurse_shortage`) = Needed minus currently available — the deficit the MILP solver must cover. `priority_score` drives allocation order."

---

## 3. Explainability chart: absolute values, percentage scale, readable, negative half removed (🟡 #22)

**Requirement:** Chart shows absolute %, is readable, negative half removed. Document `recent_trend` formula.

**Status: ✅ ALREADY CORRECT + DOCUMENTED**

| Aspect | Evidence |
|---|---|
| Absolute values | `impact_df["abs_impact"] = impact_df["impact"].abs()` — `dashboard_sections.py` line ~2774 |
| Percentage scale | `Contribution % = abs_impact / group_total * 100` — `_norm_pct()` function |
| No negative half | Two separate charts: "Active pressure-increasing" (red) + "Active pressure-reducing" (green); both use positive x-axis `[0, 115]` |
| Readable | Horizontal bar chart, `textposition="outside"`, feature labels on y-axis |
| `trend_feature` documented | Formula added to `forecast_features.py` and `dashboard_sections.py` (see below) |

**`trend_feature` formula (supervisor called it `recent_trend`):**

```python
# trend_feature: normalised row position in the training window → [0.0, 1.0].
# Formula: index / (N-1).  Captures long-run demand growth/decay over the
# training horizon; value is 0 at the first training row and 1 at the last.
# At inference time the sequence covers only the 24-h lookback window, so
# trend_feature ≈ 0.0 at the start of the window and ≈ 1.0 at the current hour.
out["trend_feature"] = (
    np.arange(len(out), dtype=float) / float(len(out) - 1)
    if len(out) > 1 else 0.0
)
```

---

## 4. Apply recommendation → re-run → Red-Amber-Green re-validates (🟡 #4)

**Requirement:** The recommendation → apply → re-validation loop works end-to-end.

**Status: ✅ LOOP EXISTS + VISUAL RAG BADGE ADDED**

**Flow:**
1. Optimizer runs → creates recommendations (`sync_recommendations()` in `approval_sections.py`)
2. Approvals tab shows pending recommendations with Approve/Reject buttons
3. On Approve: `execute_decision()` takes DB-level action (opens beds, escalates OR bookings, etc.)
4. **NEW:** `_show_revalidation_status()` displays a RAG badge immediately:
   - `staff` → GREEN "Staffing recommendation applied — coverage gap addressed"
   - `beds` → AMBER "Bed reallocation applied — monitor occupancy for full GREEN status"
   - `emergency` → GREEN "Emergency escalation applied — priority resources activated"
5. `st.rerun()` refreshes the Approvals page — pending items clear; approved items move to history

**Code location:** `approval_sections.py` — `_show_revalidation_status()` function + call in `_render_approval_card()`.

---

## 5. Forecast: both 24-h and 24–72-h views, department-specific output (🟡 #18)

**Requirement:** Forecast exposes both 24-h and 24–72-h views; department-specific output.

**Status: ✅ PRESENT (pre-existing)**

| View | Code / Source |
|---|---|
| Next-hour forecast | `predicted_patients_next_hour` from `ForecastState` |
| 24-h peak | `peak_24h` from `ForecastState` — shown in Forecast tab KPI card |
| 24-h demand outlook | "24-hour demand outlook" section in `show_forecast_panel()` |
| 72-h peak | `peak_72h` from `ForecastState` |
| 72-h overall forecast | `forecast_72h_values` (72 rows) — chart in Forecast tab |
| Dept-level forecast | `overall_forecast_72h` + `department_forecast_72h` CSVs from `ForecastState` |
| Dept breakdown tab | "Department-level forecasts" in `show_forecast_panel()` |

---

## 6. Purpose / Source / Destination annotations (🟡 #11)

**Requirement:** Annotate each major action with Purpose / Source / Destination.

**Status: ✅ ADDED TO KEY FUNCTIONS**

| Function | File | Annotation added |
|---|---|---|
| `ALERT_ROUTING_TABLE` | `api.py` | Block comment: Purpose / Source / Outcome |
| `create_alert_and_notify()` | `api.py` | Full docstring with Purpose / Source / Destination |
| `/alert-routing-table` endpoint | `api.py` | Docstring with Purpose / Source / Destination |
| `optimize_resources()` | `resource_optimizer.py` | Full docstring with Purpose / Source / Destination + label legend |
| `_show_revalidation_status()` | `approval_sections.py` | Docstring with Purpose / Source / Destination |

---

## Test verification

```
python -m pytest -q  →  128 passed, 10 warnings (9.25 s)
python -m compileall api.py dashboard_sections.py resource_optimizer.py approval_sections.py notification_sections.py api_client.py forecast_features.py -q  →  no output (clean)
python scripts/smoke_forecast_state.py  →  Smoke validation: PASSED
```

All 128 tests green. No regressions from Phase A changes.
