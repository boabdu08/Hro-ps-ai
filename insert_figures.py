"""Insert PNG figure references into HRO-PS thesis/paper markdown at *(diagram)* callouts.

Reads the source .md, replaces each *(diagram)* marker with the matching
![caption](path) image embed, writes a temporary _with_figs.md, then calls
pandoc to produce the final .docx.
"""
import re
import subprocess
import sys
from pathlib import Path

BASE = Path(r"D:\Hro new dashboard")
FIGS = BASE / "thesis_figures"
SHOTS = FIGS / "screenshots"
PANDOC = r"C:\Users\Ab005\AppData\Local\Pandoc\pandoc.exe"

# Map figure numbers (from the thesis text) to PNG paths and captions
# Key = text fragment that appears just before *(diagram)*
# Value = (png_path_relative_to_md, alt_text)
FIGURE_MAP = [
    # (search_phrase_near_marker, image_path, alt)
    ("Figure 3.1", str(FIGS / "fig_architecture.png"), "HRO-PS System Architecture block diagram"),
    ("Figure 3.2", str(FIGS / "fig_workflow.png"),     "HRO-PS Operational workflow flowchart"),
    ("Figure 4.1", str(FIGS / "fig_architecture.png"), "HRO-PS Runtime architecture"),
    ("Figure 4.2", str(FIGS / "fig_deployment.png"),   "HRO-PS Deployment topology"),
    ("Figure 5.1", str(FIGS / "fig_forecasting_pipeline.png"), "Forecasting pipeline"),
    ("Figure 5.2", str(FIGS / "fig_results_metrics.png"), "Model evaluation metrics comparison"),
    ("Figure 2.1", str(FIGS / "fig_results_metrics.png"), "Forecasting model performance comparison"),
    ("Figure 6.1", str(SHOTS / "05_optimization.jpg"), "MILP optimisation output"),
    ("Figure 7.1", str(SHOTS / "01_command_center.jpg"), "Command Centre dashboard"),
    ("Figure 7.2", str(SHOTS / "04_digital_twin.jpg"), "Digital Twin view"),
    ("Figure 7.3", str(SHOTS / "07_what_if_simulation.jpg"), "What-if simulation"),
    ("Figure 7.4", str(SHOTS / "08_explainability.jpg"), "Explainability feature sensitivity"),
]

DIAGRAM_RE = re.compile(r"\*\(diagram\)\*")


def process_md(src: Path, dst: Path) -> None:
    text = src.read_text(encoding="utf-8")
    lines = text.split("\n")
    out_lines = []
    used = set()

    for line in lines:
        if "*(diagram)*" in line:
            matched = False
            for fig_key, img_path, alt in FIGURE_MAP:
                if fig_key in line and fig_key not in used:
                    # Replace *(diagram)* with image embed on the next line
                    clean = DIAGRAM_RE.sub("", line).rstrip()
                    img_path_escaped = img_path.replace("\\", "/")
                    out_lines.append(clean)
                    out_lines.append("")
                    out_lines.append(f"![{alt}]({img_path_escaped})")
                    out_lines.append("")
                    used.add(fig_key)
                    matched = True
                    break
            if not matched:
                out_lines.append(line)
        else:
            out_lines.append(line)

    dst.write_text("\n".join(out_lines), encoding="utf-8")
    print(f"Written: {dst} ({len(used)} figures inserted)")


def compile_docx(md: Path, docx: Path, extra_flags: list) -> None:
    cmd = [PANDOC, str(md), "-o", str(docx),
           f"--resource-path={FIGS}",
           f"--resource-path={SHOTS}"] + extra_flags
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode == 0:
        size_kb = docx.stat().st_size // 1024
        print(f"Compiled: {docx.name} ({size_kb} KB)")
    else:
        print(f"pandoc ERROR for {docx.name}:\n{result.stderr[:500]}")


if __name__ == "__main__":
    # Thesis
    thesis_src = BASE / "HRO-PS_Thesis_REVISED.md"
    thesis_tmp = BASE / "HRO-PS_Thesis_REVISED_with_figs.md"
    thesis_out = BASE / "HRO-PS_Thesis_REVISED.docx"
    process_md(thesis_src, thesis_tmp)
    compile_docx(thesis_tmp, thesis_out,
                 ["--toc", "--toc-depth=3", "--number-sections"])

    # Paper
    paper_src = BASE / "HRO-PS_Paper_REVISED.md"
    paper_tmp = BASE / "HRO-PS_Paper_REVISED_with_figs.md"
    paper_out = BASE / "HRO-PS_Paper_REVISED.docx"
    process_md(paper_src, paper_tmp)
    compile_docx(paper_tmp, paper_out, ["--number-sections"])

    # Clean up temp files
    for tmp in [thesis_tmp, paper_tmp]:
        if tmp.exists():
            tmp.unlink()
    print("Done.")
