"""
Phase 10 — Insert PNG/JPG figures into thesis at *(diagram)* and *(screenshot)* callouts.
Produces HRO-PS_Thesis_REVISED_with_figs.md then compiles to DOCX.
"""
import re
import subprocess
from pathlib import Path

BASE   = Path(r"D:\Hro new dashboard")
FIGS   = BASE / "thesis_figures"
SHOTS  = FIGS / "screenshots"
PANDOC = r"C:\Users\Ab005\AppData\Local\Pandoc\pandoc.exe"

# -----------------------------------------------------------------------
# Figure map:  key = figure-number text appearing on the same line as the marker
#              value = (image_path, alt_text)
# -----------------------------------------------------------------------
def p(fname): return str(FIGS / fname)
def s(fname): return str(SHOTS / fname)

FIGURE_MAP = [
    # --- diagrams ---
    ("Figure 2.1", p("fig_results_metrics.png"),
     "Comparison of forecasting model performance (LSTM, ARIMAX, Hybrid)"),

    ("Figure 3.1", p("fig_architecture.png"),
     "HRO-PS system block diagram"),

    ("Figure 3.2", p("fig_workflow.png"),
     "HRO-PS operational workflow flowchart"),

    ("Figure 4.1", p("fig_architecture.png"),
     "Overall HRO-PS system architecture"),

    ("Figure 6.1", p("fig_deployment.png"),
     "Recommended HRO-PS deployment architecture"),

    # --- screenshots ---
    # Ch 4 — implementation
    ("Figure 4.2",  s("02_forecast_tab.jpg"),
     "Forecast tab showing patient demand data derived from the synthetic dataset"),

    ("Figure 4.3",  s("02_forecast_tab.jpg"),
     "Hybrid forecast breakdown: LSTM 0.80 / ARIMAX 0.20 weights, Hybrid MAE 8.31 RMSE 10.22"),

    ("Figure 4.4",  s("swagger_ui_page1.jpg"),
     "FastAPI interactive API documentation for HRO-PS services"),

    ("Figure 4.5",  s("01_command_center.jpg"),
     "HRO-PS Command Center — main dashboard overview"),

    ("Figure 4.6",  s("17_home_tab.jpg"),
     "Home tab showing bed occupancy (43/172), staff availability, and active alerts"),

    ("Figure 4.7",  s("02_forecast_tab.jpg"),
     "Forecast and demand-analysis panel"),

    ("Figure 4.8",  s("03_forecast_detail.jpg"),
     "72-hour forecast chart and weekly patient heatmap"),

    ("Figure 4.9",  s("04_digital_twin.jpg"),
     "Digital Twin view for hospital scenario planning"),

    ("Figure 4.10", s("05_optimization.jpg"),
     "MILP resource optimiser: beds 77, doctors 14, nurses 21 needed; ER top priority"),

    ("Figure 4.11", s("09_operations_center.jpg"),
     "Department status and capacity monitoring across 5 departments"),

    ("Figure 4.12", s("08_explainability.jpg"),
     "Explainability panel showing feature sensitivity on current forecast"),

    ("Figure 4.13", s("17_home_tab.jpg"),
     "User session panel showing role-based login (Hospital Admin, admin role)"),

    ("Figure 4.14", s("13_notifications.jpg"),
     "Alert and notification centre with warning and critical alerts"),

    ("Figure 4.15", s("10_shifts.jpg"),
     "Staff shift-management interface showing scheduled shifts by department"),

    ("Figure 4.16", s("12_or_bookings.jpg"),
     "Operating-room booking management interface"),

    ("Figure 4.17", s("11_appointments.jpg"),
     "Appointment overview across departments"),

    ("Figure 4.18", s("14_approvals.jpg"),
     "Administrative approval-workflow panel for AI-generated recommendations"),

    ("Figure 4.19", s("13_notifications.jpg"),
     "Notifications and alert feed for operational decisions"),

    ("Figure 4.20", s("15_audit.jpg"),
     "Audit and execution-trace interface for decision traceability"),

    # Ch 5 — evaluation
    ("Figure 5.1",  s("06_evaluation.jpg"),
     "Evaluation tab: LSTM MAE 7.64/RMSE 9.58, ARIMAX 15.63/19.33, Hybrid 8.31/10.22"),

    ("Figure 5.2",  s("02_forecast_tab.jpg"),
     "Forecast and demand-analysis results in the dashboard"),

    ("Figure 5.3",  s("03_forecast_detail.jpg"),
     "Actual-versus-forecast comparison for the recent evaluation window"),

    ("Figure 5.4",  s("03_forecast_detail.jpg"),
     "Weekly patient-load heatmap for demand-intensity evaluation"),

    ("Figure 5.5",  s("08_explainability.jpg"),
     "Explainability output: active pressure-increasing and pressure-reducing feature drivers"),

    ("Figure 5.6",  s("05_optimization.jpg"),
     "MILP resource-optimisation output based on predicted hospital demand"),

    ("Figure 5.7",  s("04_digital_twin.jpg"),
     "Digital Twin forecast horizon results for capacity planning"),

    ("Figure 5.8",  s("01_command_center.jpg"),
     "Integrated command-centre dashboard: forecast, KPIs, capacity, alerts"),

    ("Figure 5.9",  s("10_shifts.jpg"),
     "Shift-management results in the dashboard"),

    ("Figure 5.10", s("12_or_bookings.jpg"),
     "Operating-room booking results"),

    ("Figure 5.11", s("11_appointments.jpg"),
     "Appointment overview and booking management results"),
]

MARKER_RE = re.compile(r'\*\((diagram|screenshot)\)\*')


def process_md(src: Path, dst: Path) -> int:
    text = src.read_text(encoding="utf-8")
    lines = text.split("\n")
    out_lines = []
    used: set = set()
    inserted = 0

    for line in lines:
        if MARKER_RE.search(line):
            matched = False
            for fig_key, img_path, alt in FIGURE_MAP:
                if fig_key in line and fig_key not in used:
                    clean = MARKER_RE.sub("", line).rstrip()
                    img_path_escaped = img_path.replace("\\", "/")
                    out_lines.append(clean)
                    out_lines.append("")
                    out_lines.append(f"![{alt}]({img_path_escaped})")
                    out_lines.append("")
                    used.add(fig_key)
                    matched = True
                    inserted += 1
                    break
            if not matched:
                out_lines.append(line)   # keep line as-is (no match)
        else:
            out_lines.append(line)

    dst.write_text("\n".join(out_lines), encoding="utf-8")
    print(f"  Written temp md: {dst.name} ({inserted} figures inserted)")
    return inserted


def compile_docx(md: Path, docx: Path, extra_flags: list) -> None:
    cmd = [PANDOC, str(md), "-o", str(docx),
           f"--resource-path={FIGS}",
           f"--resource-path={SHOTS}",
           f"--resource-path={BASE}"] + extra_flags
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode == 0:
        size_kb = docx.stat().st_size // 1024
        print(f"  Compiled: {docx.name} ({size_kb} KB)")
    else:
        print(f"  pandoc ERROR for {docx.name}:")
        print(result.stderr[:800])


if __name__ == "__main__":
    print("=== Thesis ===")
    thesis_src = BASE / "HRO-PS_Thesis_REVISED.md"
    thesis_tmp = BASE / "HRO-PS_Thesis_REVISED_with_figs.md"
    thesis_out = BASE / "HRO-PS_Thesis_REVISED.docx"

    n = process_md(thesis_src, thesis_tmp)
    print(f"  ({n} figure callouts resolved)")
    compile_docx(thesis_tmp, thesis_out,
                 ["--toc", "--toc-depth=3", "--number-sections"])

    # Cleanup temp file
    if thesis_tmp.exists():
        thesis_tmp.unlink()

    print("\n=== Paper ===")
    paper_src = BASE / "HRO-PS_Paper_REVISED.md"
    paper_tmp = BASE / "HRO-PS_Paper_REVISED_with_figs.md"
    paper_out = BASE / "HRO-PS_Paper_REVISED.docx"

    n = process_md(paper_src, paper_tmp)
    print(f"  ({n} figure callouts resolved)")
    compile_docx(paper_tmp, paper_out, ["--number-sections"])

    if paper_tmp.exists():
        paper_tmp.unlink()

    print("\nDone.")
