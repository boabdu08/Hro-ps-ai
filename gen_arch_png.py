"""Generate fig_architecture.png using Pillow (fallback for systems without Cairo)."""
import math
import os
from PIL import Image, ImageDraw

W, H = 2080, 1200
img = Image.new("RGB", (W, H), "#f6f7fb")
draw = ImageDraw.Draw(img)


def hex_to_rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))


def box(x, y, w, h, fill, border, lines, text_color="#1b2333"):
    fill_rgb = hex_to_rgb(fill)
    border_rgb = hex_to_rgb(border)
    draw.rounded_rectangle([x, y, x+w, y+h], radius=14, fill=fill_rgb, outline=border_rgb, width=3)
    lh = max((h - 20) // max(len(lines), 1), 22)
    for i, line in enumerate(lines):
        ty = y + 14 + i * lh
        draw.text((x + w // 2, ty), line, fill=hex_to_rgb(text_color), anchor="mt")


def arrow(x1, y1, x2, y2):
    draw.line([(x1, y1), (x2, y2)], fill=hex_to_rgb("#33415c"), width=4)
    angle = math.atan2(y2 - y1, x2 - x1)
    sz = 20
    for da in (0.45, -0.45):
        ax = int(x2 - sz * math.cos(angle - da))
        ay = int(y2 - sz * math.sin(angle - da))
        draw.polygon([(x2, y2), (ax, ay)], fill=hex_to_rgb("#33415c"))


# Title
draw.text((W // 2, 30), "HRO-PS  System Architecture", fill=hex_to_rgb("#1b2333"), anchor="mt")
draw.text((W // 2, 72), "Forecast  →  Validate  →  Optimise  →  Simulate  →  Explain  →  Approve  →  Audit",
          fill=hex_to_rgb("#5b6b86"), anchor="mt")

# Data layer
box(60, 170, 400, 240, "#eef2fb", "#2f5496",
    ["Synthetic Dataset", "17,520 rows × 61 cols", "2 years · 5 departments", "Feature engineering (~25 cols)"])

# Forecasting core
box(560, 150, 450, 280, "#e3eefc", "#2e86ab", ["Forecasting Core"])
draw.rounded_rectangle([580, 232, 990, 316], radius=12,
                        fill=hex_to_rgb("#2e86ab"), outline=hex_to_rgb("#1a6080"), width=2)
draw.text((785, 268), "LSTM  (weight 0.80)", fill=(255, 255, 255), anchor="mm")
draw.rounded_rectangle([580, 330, 990, 400], radius=12,
                        fill=hex_to_rgb("#8fb8d6"), outline=hex_to_rgb("#2e86ab"), width=2)
draw.text((785, 366), "ARIMAX  (weight 0.20)", fill=hex_to_rgb("#1b2333"), anchor="mm")
draw.text((785, 420), "→ Hybrid (constrained blend, 0.80/0.20)", fill=hex_to_rgb("#33415c"), anchor="mt")

# ForecastState
box(1100, 170, 380, 250, "#2f5496", "#22406f",
    ["ForecastState", "single source of truth", "next-hour · 24h/72h peak", "72h avg · model status", "metrics · optimiser input"],
    text_color="#dce6f7")

# Consumers
box(1600, 150, 420, 80, "#fff3e0", "#e08a2e", ["MILP optimiser  (scipy.optimize.milp)"])
box(1600, 248, 420, 74, "#eaf6ee", "#3c9f5e", ["Digital Twin  (72h forecast)"])
box(1600, 340, 420, 74, "#eaf6ee", "#3c9f5e", ["What-if simulation"])
box(1600, 432, 420, 74, "#eaf6ee", "#3c9f5e", ["Explainability  ·  Evaluation"])

# Horizontal arrows — data→models, models→state, state→consumers
arrow(462, 290, 558, 290)
arrow(1012, 290, 1098, 290)
arrow(1482, 240, 1598, 195)
arrow(1482, 278, 1598, 285)
arrow(1482, 320, 1598, 375)
arrow(1482, 360, 1598, 465)

# Label on state→consumers arrow
draw.text((1300, 520), "canonical values feed every API and tab", fill=hex_to_rgb("#5b6b86"), anchor="mt")

# FastAPI
box(560, 600, 840, 140, "#eef2fb", "#2f5496",
    ["FastAPI backend", "48 REST endpoints · PostgreSQL (21 tables) · bcrypt + JWT"])

# Dashboard
box(560, 780, 840, 160, "#e3eefc", "#2e86ab",
    ["Streamlit command-centre dashboard", "Role-based views: admin · doctor · nurse",
     "Command Center · Forecast · Optimization · Digital Twin · Evaluation · Explainability"])

# Workflow
box(560, 980, 840, 130, "#f6f7fb", "#8a93a6",
    ["Workflow & coordination", "Shifts · Appointments · OR bookings",
     "Notifications · Messages · Approvals · Audit"])

# State → FastAPI vertical arrow
arrow(1290, 422, 980, 600)
# FastAPI → Dashboard
arrow(980, 742, 980, 778)
# Dashboard → Workflow
arrow(980, 942, 980, 978)

# Footer
draw.text((60, H - 38), "Prototype on synthetic/demo data — not clinically validated; no live HIS/EHR integration.",
          fill=hex_to_rgb("#5b6b86"))

out = r"D:\Hro new dashboard\thesis_figures\fig_architecture.png"
img.save(out, dpi=(200, 200))
sz = os.path.getsize(out) // 1024
print(f"Saved {sz} KB -> {out}")
