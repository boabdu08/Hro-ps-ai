# Claude Code — Phase 10: Close the Document Gaps

> The previous compile pass produced the files but (a) synced the PPTX text only shallowly and **skipped table cells**, (b) embedded **no figures in the paper**, and (c) used **unverified** screenshot names. This prompt fixes those. Paste the block below.

## PASTE THIS INTO CLAUDE CODE

Finalize the remaining document gaps. You may read/write in `D:\Hro new dashboard`; never overwrite my original uploads — regenerate the `*_FINAL` / `*_REVISED` outputs. After any code change, re-run `pytest` and keep all 128 tests green.

### A) Presentation — do a PROPER sync (the previous pass changed only 4 runs and skipped tables)
Open `D:\Hospital Resource Optimization with AI Final Hro.pptx`. Iterate **every** shape, **including tables and speaker notes**:
```
for slide in prs.slides:
    for shape in slide.shapes:
        if shape.has_text_frame: <patch runs>
        if shape.has_table:
            for row in shape.table.rows:
                for cell in row.cells:
                    for p in cell.text_frame.paragraphs:
                        for run in p.runs: <patch runs>
```
Save as `HRO-PS_Presentation_FINAL.pptx`. Specific fixes:
- **Slide 13 "Model Comparison" TABLE** → set canonical metrics: **LSTM MAE 7.65 / RMSE 9.58 / MAPE 5.52% (most accurate)**; **ARIMAX 15.63 / 19.33 / 12.33% (baseline)**; **Hybrid 0.80/0.20 → 8.31 / 10.22 / 6.07% (deployed for robustness)**. Delete any other metric values (7.32, 9.83, 7.76, 6.6, 8.1, 4.9, 94%). This table must NOT contradict the results chart already on the slide.
- **Slide 15** title "24‑Hour Demand Predictions" → "72‑Hour Demand Forecast" (24 h is only the LSTM input window; the forecast horizon is 72 h).
- **Slide 9** "HL7/FHIR integration", "two‑stage optimization" → reframe as **design/future**, not built (prototype = synthetic CSV ingestion + MILP resource optimiser).
- **Slide 14** hybrid weighting → show **0.80 / 0.20** (α = 0.80).
- **Slide 5** "Industrial Partner: El Demerdash Hospital" → keep, but reword to "site visit / clinical context" consistent with the thesis (no real patient data was shared).
- Global, metric‑context only: "rule‑based" optimiser → "MILP (`scipy.optimize.milp`)"; "29,302"/"3+ years" → "17,520 / 2 years". Remove "94%/94.17%/25.5%/18–22% productivity". **Do NOT blanket‑replace "94%" with arbitrary words** — only correct it where it's a metric.
- **Slide 10**: confirm the newly inserted architecture image doesn't overlap an old block‑diagram image; if it does, remove/shrink the old one.
- Add 2–3 speaker‑note lines to the key slides from the jury Q&A in `HRO-PS_Presentation_Content_and_Sync.md` via `slide.notes_slide.notes_text_frame`.

### B) Paper — recompile (3 figures were just added to the markdown)
```
pandoc "D:\Hro new dashboard\HRO-PS_Paper_REVISED.md" -o "D:\Hro new dashboard\HRO-PS_Paper_REVISED.docx" --number-sections --resource-path="D:\Hro new dashboard"
```
Confirm the architecture, pipeline, and results figures are embedded (file size should jump well above 23 KB).

### C) Screenshots — verify before trusting the names (they are currently guesses)
Preferred: capture **live** — `python seed_from_csv.py`, then `uvicorn api:app --port 8000` and `streamlit run dashboard.py`; log in `admin1` / `123456`; screenshot each tab (Command Center, Forecast, Evaluation, Optimization, Digital Twin, What‑if, Explainability, Departments, Shifts, Appointments, OR, Notifications/Approvals/Audit, Swagger). Save to `D:\Hro new dashboard\thesis_figures\screenshots\` with correct names, replacing the renamed PDF exports. If you can't run the GUI, open each `HRO Command Center N.pdf` and rename by actual content. Then re‑insert the correct images anywhere they're referenced.

### D) Thesis — embed dashboard screenshots at the `*(screenshot)*` callouts (Figures 4.x, 5.x) using the verified images, then recompile:
```
pandoc "D:\Hro new dashboard\HRO-PS_Thesis_REVISED.md" -o "D:\Hro new dashboard\HRO-PS_Thesis_REVISED.docx" --toc --toc-depth=3 --number-sections --resource-path="D:\Hro new dashboard"
```

### E) Poster — the previous pass changed only 3 strings. Rebuild the poster text from `HRO-PS_Poster_Content.md` (sections 0–8) onto the existing single slide, preserving the theme; insert `fig_architecture.png`, `fig_forecasting_pipeline.png`, `fig_results_metrics.png`, and the verified Optimization + Command Center screenshots. Save `HRO-PS_Poster_FINAL.pptx`.

### Report
List, per file, exactly what changed, and flag any figure slot you couldn't fill or any slide you couldn't safely edit.
