# Claude Code — Phase 8 & 9: Compile Documents + Capture Screenshots

> Paste the block below into Claude Code (repo open in VS Code). It finishes the two steps left open by the hardening run. You are authorized to read/write in `D:\Hro new dashboard`. **Never overwrite my original uploads — always write NEW files.**

## PASTE THIS INTO CLAUDE CODE

Continue with Phases 8 and 9 from FINALIZE_WITH_CLAUDE_CODE.md. Authorized to read/write in `D:\Hro new dashboard`. Do not overwrite original uploads; always save new files. Steps:

1. **Tooling.** Ensure `pandoc` is available; `pip install python-docx python-pptx cairosvg` if missing.

2. **Diagrams → PNG.** Convert every `D:\Hro new dashboard\thesis_figures\*.svg` to PNG at ~200 DPI (cairosvg). Keep the same base names.

3. **Compile the documents** (embed the PNG diagrams at the figure callouts in the markdown):
   - `HRO-PS_Thesis_REVISED.md` → `HRO-PS_Thesis_REVISED.docx`  (`--toc --toc-depth=3 --number-sections`)
   - `HRO-PS_Paper_REVISED.md` → `HRO-PS_Paper_REVISED.docx`  (`--number-sections`)
   Save both in `D:\Hro new dashboard`.

4. **Screenshots (Phase 9).** Seed if needed (`python seed_from_csv.py`), then run `uvicorn api:app --port 8000` and `streamlit run dashboard.py`. Log in as `admin1` / `123456` (tenant `demo-hospital`). Capture clean PNGs of: Command Center, Forecast (LSTM/ARIMAX/Hybrid), Evaluation (MAE/RMSE/MAPE), Optimization (MILP allocation + solver status), Digital Twin, What‑if, Explainability, Department status, Shifts, Appointments, OR bookings, Notifications/Approvals/Audit, and the Swagger UI. Save to `D:\Hro new dashboard\thesis_figures\screenshots\` with descriptive names.

5. **Poster & presentation — PRESERVE the existing theme (no restyle).** With python‑pptx, apply the corrected content + sync checklists in `D:\Hro new dashboard\HRO-PS_Poster_Content.md` and `HRO-PS_Presentation_Content_and_Sync.md` onto the existing decks — poster `poster msa.pptx` (in the uploads folder), presentation `Hospital Resource Optimization with AI Final Hro.pptx`. Replace only outdated text/numbers; insert the PNG diagrams and the step‑4 screenshots. Save as `HRO-PS_Poster_FINAL.pptx` and `HRO-PS_Presentation_FINAL.pptx` in `D:\Hro new dashboard`.

6. **(Recommended) Fix the dual model path.** Point `/predict` and `/explain` (`forecast_inference.py` / root models) at the same 72h models the dashboard uses (`artifacts/models_72h/*`) so Explainability metrics match the displayed metrics — or, if risky, add a one‑line UI note that Explainability is a separate sensitivity view. Re‑run `pytest` afterward and keep all tests green.

7. **Report** which files you produced and any figure slots you couldn't fill.
