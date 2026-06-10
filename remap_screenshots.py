"""
Remap screenshots from guessed sequential names to verified content-based names.

Source JPGs:  D:\Hro new dashboard\HRO Command Center{N}_page-0001.jpg
Target dir:   D:\Hro new dashboard\thesis_figures\screenshots\

Verified mapping (inspected page-by-page):
  PDF  1 p1 = Home tab (artifact mode)
  PDF  2 p1 = Home tab (live API mode)
  PDF  3 p1 = Command Center tab
  PDF  4 p1 = Forecast tab
  PDF  5 p1 = Optimization tab
  PDF  6 p1 = Operations Center > Operations (dept allocations)
  PDF  7 p1 = Operations Center > Simulation (MEDIUM)
  PDF  8 p1 = Operations Center > Simulation (HIGH)
  PDF  9 p1 = Operations Center > Digital Twin
  PDF 10 p1 = Operations Center > Dept Status (ER)
  PDF 11 p1 = Operations Center > Dept Status (ICU)
  PDF 12 p1 = Operations Center > Dept Status (General Ward)
  PDF 13 p1 = Shifts tab
  PDF 14 p1 = Appointments tab
  PDF 15 p1 = OR Bookings tab
  PDF 16 p1 = Notifications tab (Alerts)
  PDF 17 p1 = Messages tab
  PDF 18 p1 = Approvals tab
  PDF 19 p1 = Evaluation tab  ← has the canonical MAE/RMSE metrics table
  PDF 20 p1 = Explainability tab (Model Feature Sensitivity)
  PDF 21 p1 = Audit tab
"""
import shutil
from pathlib import Path

SRC = Path(r"D:\Hro new dashboard")
DST = Path(r"D:\Hro new dashboard\thesis_figures\screenshots")

# (target_name, source_file)
REMAP = [
    # Core dashboard tabs
    ("01_command_center.jpg",     "HRO Command Center3_page-0001.jpg"),
    ("02_forecast_tab.jpg",       "HRO Command Center4_page-0001.jpg"),
    ("03_forecast_detail.jpg",    "HRO Command Center4_page-0002.jpg"),
    ("04_digital_twin.jpg",       "HRO Command Center9_page-0001.jpg"),
    ("05_optimization.jpg",       "HRO Command Center5_page-0001.jpg"),
    ("06_evaluation.jpg",         "HRO Command Center19_page-0001.jpg"),  # ← canonical metrics!
    ("07_what_if_simulation.jpg", "HRO Command Center7_page-0001.jpg"),
    ("08_explainability.jpg",     "HRO Command Center20_page-0001.jpg"),
    ("09_operations_center.jpg",  "HRO Command Center6_page-0001.jpg"),
    # Workflow tabs
    ("10_shifts.jpg",             "HRO Command Center13_page-0001.jpg"),
    ("11_appointments.jpg",       "HRO Command Center14_page-0001.jpg"),
    ("12_or_bookings.jpg",        "HRO Command Center15_page-0001.jpg"),
    ("13_notifications.jpg",      "HRO Command Center16_page-0001.jpg"),
    ("14_approvals.jpg",          "HRO Command Center18_page-0001.jpg"),
    ("15_audit.jpg",              "HRO Command Center21_page-0001.jpg"),
    ("16_messages.jpg",           "HRO Command Center17_page-0001.jpg"),
    ("17_home_tab.jpg",           "HRO Command Center1_page-0001.jpg"),
    # Detail pages
    ("18_optimization_detail.jpg","HRO Command Center5_page-0002.jpg"),
    ("19_digital_twin_detail.jpg","HRO Command Center9_page-0002.jpg"),
    ("20_simulation_high.jpg",    "HRO Command Center8_page-0001.jpg"),
    ("21_audit_detail.jpg",       "HRO Command Center21_page-0002.jpg"),
    # Evaluation detail (page 2 shows model comparison charts)
    ("22_evaluation_detail.jpg",  "HRO Command Center19_page-0002.jpg"),
    # Swagger UI stays the same
    # ("swagger_ui_page1.jpg" already correct)
]

print(f"Remapping {len(REMAP)} screenshots...\n")
ok = 0
skip = 0
for target_name, src_name in REMAP:
    src_path = SRC / src_name
    dst_path = DST / target_name
    if src_path.exists():
        shutil.copy2(str(src_path), str(dst_path))
        print(f"  OK  {target_name}  <-  {src_name}")
        ok += 1
    else:
        print(f"  MISS  {src_name}  (skipped {target_name})")
        skip += 1

print(f"\n{ok} copied, {skip} skipped.")
print("\nFinal screenshots directory:")
for f in sorted(DST.glob("*.jpg")):
    sz = f.stat().st_size // 1024
    print(f"  {f.name}  ({sz} KB)")
