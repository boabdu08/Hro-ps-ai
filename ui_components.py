from __future__ import annotations

import re

import streamlit as st


# ------------------------------
# Premium design system (tokens)
# ------------------------------


UI_THEME_KEY = "ui_theme_mode"
UI_BUILD_ID = "2026-03-26-ui-refresh"


# ------------------------------
# Design system tokens
# Apple/Stripe-inspired medical palette
# ------------------------------


TOKENS_LIGHT = {
    # Canvas
    "bg": "#F7F9FB",  # soft off-white
    "bg_elev": "#FFFFFF",
    "bg_muted": "#F1F5F9",  # slate-100

    # Text
    "text": "#1F2937",  # gray-800
    "text_2": "#6B7280",  # gray-500
    "text_3": "#9CA3AF",  # gray-400

    # Brand
    "primary": "#3B82F6",  # blue-500
    "secondary": "#14B8A6",  # teal-500
    "accent": "#6366F1",  # indigo-500

    # Status
    "success": "#22C55E",
    "warning": "#F59E0B",
    "critical": "#EF4444",
    "info": "#3B82F6",

    # Borders + elevation
    "border": "rgba(15, 23, 42, 0.10)",
    "border_strong": "rgba(59, 130, 246, 0.25)",
    "shadow_sm": "0 1px 2px rgba(15, 23, 42, 0.06), 0 1px 1px rgba(15, 23, 42, 0.04)",
    "shadow": "0 10px 28px rgba(15, 23, 42, 0.10)",
    "shadow_hover": "0 14px 36px rgba(15, 23, 42, 0.14)",

    # Radius
    "radius_card": "16px",
    "radius_btn": "10px",
    "radius_input": "10px",
}


TOKENS_DARK = {
    # Canvas
    "bg": "#0B1220",  # deep slate
    "bg_elev": "#0F172A",  # slate-900
    "bg_muted": "#111C31",

    # Text
    "text": "#E5E7EB",  # gray-200
    "text_2": "rgba(229, 231, 235, 0.72)",
    "text_3": "rgba(229, 231, 235, 0.55)",

    # Brand
    "primary": "#60A5FA",  # blue-400
    "secondary": "#2DD4BF",  # teal-400
    "accent": "#818CF8",  # indigo-400

    # Status
    "success": "#34D399",
    "warning": "#FBBF24",
    "critical": "#FB7185",
    "info": "#60A5FA",

    # Borders + elevation
    "border": "rgba(148, 163, 184, 0.14)",
    "border_strong": "rgba(96, 165, 250, 0.35)",
    "shadow_sm": "0 1px 2px rgba(0, 0, 0, 0.30)",
    "shadow": "0 12px 32px rgba(0, 0, 0, 0.42)",
    "shadow_hover": "0 16px 44px rgba(0, 0, 0, 0.52)",

    # Radius
    "radius_card": "16px",
    "radius_btn": "10px",
    "radius_input": "10px",
}


def get_theme_mode() -> str:
    """Return current UI theme mode: 'light' or 'dark'."""

    mode = (st.session_state.get(UI_THEME_KEY) or "light").strip().lower()
    return "dark" if mode == "dark" else "light"


def set_theme_mode(mode: str) -> None:
    mode = (mode or "light").strip().lower()
    st.session_state[UI_THEME_KEY] = "dark" if mode == "dark" else "light"


def theme_tokens() -> dict:
    return TOKENS_DARK if get_theme_mode() == "dark" else TOKENS_LIGHT


def plotly_template_name() -> str:
    return "plotly_dark" if get_theme_mode() == "dark" else "plotly_white"


def _escape_html(text: str) -> str:
    # Streamlit isn't a full templating engine; do minimal escaping.
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def inject_base_styles():
    """Inject global CSS for a calm medical SaaS aesthetic.

    NOTE: This function is intentionally pure-UI; it should not affect business logic.
    """

    tokens = theme_tokens()

    # Best-effort plotly theming (presentation-only).
    try:
        import plotly.io as pio

        pio.templates.default = plotly_template_name()
    except Exception:
        pass

    st.markdown(
        """
        <style>
        :root {
          --bg: """ + tokens["bg"] + """;
          --bg-elev: """ + tokens["bg_elev"] + """;
          --bg-muted: """ + tokens["bg_muted"] + """;
          --text: """ + tokens["text"] + """;
          --text-2: """ + tokens["text_2"] + """;
          --text-3: """ + tokens["text_3"] + """;
          --primary: """ + tokens["primary"] + """;
          --secondary: """ + tokens["secondary"] + """;
          --accent: """ + tokens["accent"] + """;
          --success: """ + tokens["success"] + """;
          --warning: """ + tokens["warning"] + """;
          --critical: """ + tokens["critical"] + """;
          --border: """ + tokens["border"] + """;
          --border-strong: """ + tokens["border_strong"] + """;
          --shadow-sm: """ + tokens["shadow_sm"] + """;
          --shadow: """ + tokens["shadow"] + """;
          --shadow-hover: """ + tokens["shadow_hover"] + """;
          --radius-card: """ + tokens["radius_card"] + """;
          --radius-btn: """ + tokens["radius_btn"] + """;
          --radius-input: """ + tokens["radius_input"] + """;
          --trans-fast: 140ms;
          --trans-med: 220ms;
        }

        /* Canvas */
        html, body {
          background: var(--bg) !important;
          color: var(--text) !important;
        }

        /* Canvas */
        .stApp {
          background: linear-gradient(180deg, var(--bg) 0%, var(--bg) 65%, var(--bg-muted) 100%) !important;
          color: var(--text) !important;
          transition: background var(--trans-med) ease, color var(--trans-med) ease;
        }

        /* Some Streamlit builds wrap content in these containers */
        div[data-testid="stAppViewContainer"],
        div[data-testid="stAppViewContainer"] > .main {
          background: transparent !important;
          color: var(--text) !important;
        }

        /* Layout rhythm */
        .main { padding-top: 0.25rem; }
        .block-container { padding-top: 1.1rem; padding-bottom: 2.8rem; max-width: 1320px; }

        /* Typography polish */
        html, body, [class*="css"]  {
          font-feature-settings: "kern" 1, "liga" 1;
          -webkit-font-smoothing: antialiased;
          text-rendering: optimizeLegibility;
        }

        /* Make markdown headings calmer + consistent */
        .stMarkdown h2, .stMarkdown h3 {
          letter-spacing: -0.01em;
          color: var(--text);
        }
        .stMarkdown h3 { margin-top: 0.25rem; }
        .stMarkdown p, .stMarkdown li { color: var(--text); }
        .stCaption { color: var(--text-2) !important; }

        /* Section headers */
        .hro-section {
          display:flex;
          align-items:flex-end;
          justify-content:space-between;
          gap: 12px;
          margin: 14px 0 10px 0;
        }
        .hro-section-title {
          font-size: 1.05rem;
          font-weight: 820;
          letter-spacing: -0.015em;
          margin: 0;
          color: var(--text);
        }
        .hro-section-subtitle {
          margin-top: 4px;
          color: var(--text-2);
          font-size: 0.92rem;
        }

        /* Page header */
        .hro-page-header {
          display:flex; justify-content:space-between; align-items:flex-end;
          gap: 12px;
          padding: 18px 18px;
          margin-bottom: 14px;
          background: linear-gradient(135deg, rgba(59,130,246,0.10), rgba(20,184,166,0.08));
          border: 1px solid var(--border-strong);
          border-radius: var(--radius-card);
          box-shadow: var(--shadow-sm);
        }
        .hro-page-title {
          font-size: 1.55rem;
          font-weight: 780;
          letter-spacing: -0.02em;
          color: var(--text);
          margin: 0;
        }
        .hro-page-subtitle {
          color: var(--text-2);
          margin-top: 0.35rem;
          font-size: 0.96rem;
        }
        .hro-header-meta {
          text-align: right;
          color: var(--text-2);
          font-size: 0.9rem;
        }

        /* Section surfaces (used by components) */
        .hro-surface {
          background: var(--bg-elev);
          border: 1px solid var(--border);
          border-radius: var(--radius-card);
          box-shadow: var(--shadow-sm);
        }

        /* KPI card */
        .hro-kpi {
          padding: 16px 16px;
          border-radius: var(--radius-card);
          background: var(--bg-elev);
          border: 1px solid var(--border);
          box-shadow: var(--shadow-sm);
          min-height: 112px;
          transition: transform var(--trans-fast) ease, box-shadow var(--trans-fast) ease, border-color var(--trans-fast) ease;
        }
        .hro-kpi:hover {
          transform: translateY(-2px);
          box-shadow: var(--shadow-hover);
          border-color: var(--border-strong);
        }
        .hro-kpi-title {
          color: var(--text-2);
          font-size: 0.86rem;
          margin-bottom: 6px;
          font-weight: 650;
        }
        .hro-kpi-value {
          color: var(--text);
          font-size: 2.05rem;
          font-weight: 820;
          letter-spacing: -0.03em;
          line-height: 1.15;
        }
        .hro-kpi-delta {
          margin-top: 8px;
          color: var(--text-2);
          font-size: 0.9rem;
        }

        /* Status accent */
        .hro-accent-normal { border-left: 6px solid rgba(59,130,246,0.85); }
        .hro-accent-success { border-left: 6px solid rgba(34,197,94,0.85); }
        .hro-accent-warning { border-left: 6px solid rgba(245,158,11,0.88); }
        .hro-accent-critical { border-left: 6px solid rgba(239,68,68,0.88); }

        /* Badges */
        .hro-badge {
          display:inline-flex;
          align-items:center;
          gap: 6px;
          padding: 4px 10px;
          border-radius: 999px;
          font-size: 12px;
          font-weight: 750;
          letter-spacing: 0.02em;
          border: 1px solid var(--border);
        }
        .hro-badge-neutral { background: rgba(148,163,184,0.14); color: var(--text); }
        .hro-badge-info { background: rgba(59,130,246,0.14); color: var(--text); border-color: rgba(59,130,246,0.22); }
        .hro-badge-success { background: rgba(34,197,94,0.14); color: var(--text); border-color: rgba(34,197,94,0.20); }
        .hro-badge-warning { background: rgba(245,158,11,0.14); color: var(--text); border-color: rgba(245,158,11,0.22); }
        .hro-badge-critical { background: rgba(239,68,68,0.14); color: var(--text); border-color: rgba(239,68,68,0.22); }

        /* Alert cards */
        .hro-alert {
          padding: 14px 14px;
          border-radius: var(--radius-card);
          background: var(--bg-elev);
          border: 1px solid var(--border);
          box-shadow: var(--shadow-sm);
        }
        .hro-alert-body { color: var(--text); opacity: 0.95; }
        .hro-alert-meta { margin-top: 8px; color: var(--text-2); font-size: 0.88rem; }

        /* Empty states */
        .hro-empty {
          text-align:center;
          padding: 34px 18px;
          border: 1px dashed rgba(148, 163, 184, 0.55);
          border-radius: var(--radius-card);
          background: rgba(148, 163, 184, 0.08);
          color: var(--text-2);
        }

        /* Streamlit native component polish */
        div[data-baseweb="input"] > div,
        div[data-baseweb="textarea"] > div,
        div[data-baseweb="select"] > div {
          border-radius: var(--radius-input) !important;
          border: 1px solid var(--border) !important;
          background: var(--bg-elev) !important;
          box-shadow: none !important;
          transition: border-color var(--trans-fast) ease;
        }
        div[data-baseweb="input"] > div:focus-within,
        div[data-baseweb="textarea"] > div:focus-within,
        div[data-baseweb="select"] > div:focus-within {
          border-color: var(--border-strong) !important;
          box-shadow: 0 0 0 3px rgba(59,130,246,0.16) !important;
        }

        .stButton > button {
          border-radius: var(--radius-btn) !important;
          border: 1px solid var(--border) !important;
          background: var(--bg-elev) !important;
          color: var(--text) !important;
          padding: 0.56rem 0.88rem !important;
          font-weight: 750 !important;
          transition: transform var(--trans-fast) ease, box-shadow var(--trans-fast) ease, border-color var(--trans-fast) ease;
        }
        .stButton > button:hover {
          transform: translateY(-1px);
          box-shadow: var(--shadow-hover);
          border-color: var(--border-strong) !important;
        }

        /* Primary buttons (Streamlit adds kind of inline styles; we reinforce) */
        .stButton > button[kind="primary"] {
          background: var(--primary) !important;
          border-color: rgba(0,0,0,0.00) !important;
          color: white !important;
        }

        /* Secondary buttons: ensure adequate contrast across themes.
           Use a very subtle tint to visually separate from cards/inputs.
           NOTE: keep primary buttons untouched. */
        .stButton > button:not([kind="primary"]) {
          background: rgba(59,130,246,0.08) !important;
        }

        /* Improve readability for Plotly charts (axes, legend) across themes */
        .js-plotly-plot .plotly .xtick text,
        .js-plotly-plot .plotly .ytick text,
        .js-plotly-plot .plotly .gtitle,
        .js-plotly-plot .plotly .legend text {
          fill: var(--text) !important;
          color: var(--text) !important;
        }

        /* Improve table readability in Streamlit's dataframe (best-effort selectors) */
        div[data-testid="stDataFrame"] [role="columnheader"],
        div[data-testid="stDataFrame"] [role="gridcell"] {
          color: var(--text) !important;
          background-color: var(--bg-elev) !important;
        }
        div[data-testid="stDataFrame"] [role="columnheader"] {
          color: var(--text) !important;
          border-bottom: 1px solid var(--border) !important;
        }

        /* Tabs */
        .stTabs [data-baseweb="tab"] {
          font-weight: 720 !important;
          color: var(--text-2) !important;
          border-radius: 10px !important;
          padding-top: 10px !important;
          padding-bottom: 10px !important;
        }
        .stTabs [data-baseweb="tab"][aria-selected="true"] {
          color: var(--text) !important;
          background: rgba(59,130,246,0.10) !important;
        }

        /* Dataframe container */
        div[data-testid="stDataFrame"] {
          border-radius: var(--radius-card);
          overflow: hidden;
          border: 1px solid var(--border);
          box-shadow: var(--shadow-sm);
          background: var(--bg-elev);
        }

        /* Better default look for st.container(border=True) */
        div[data-testid="stVerticalBlockBorderWrapper"] {
          border-radius: var(--radius-card) !important;
          border: 1px solid var(--border) !important;
          box-shadow: var(--shadow-sm) !important;
          background: var(--bg-elev) !important;
        }

        /* Sidebar */
        section[data-testid="stSidebar"] {
          background: linear-gradient(180deg, rgba(148,163,184,0.08), rgba(148,163,184,0.03)) !important;
          border-right: 1px solid var(--border);
        }

        /* Build badge (verification aid) */
        .hro-build-badge {
          position: fixed;
          right: 14px;
          bottom: 12px;
          z-index: 9999;
          padding: 6px 10px;
          border-radius: 999px;
          font-size: 12px;
          font-weight: 800;
          letter-spacing: 0.02em;
          color: var(--text);
          background: rgba(148, 163, 184, 0.16);
          border: 1px solid var(--border);
          box-shadow: var(--shadow-sm);
          backdrop-filter: blur(8px);
          -webkit-backdrop-filter: blur(8px);
          opacity: 0.82;
          pointer-events: none;
        }

        /* Sidebar navigation (radio) */
        section[data-testid="stSidebar"] div[role="radiogroup"] label {
          border-radius: 12px;
          padding: 10px 10px;
          margin: 4px 0;
          transition: background var(--trans-fast) ease, border-color var(--trans-fast) ease;
          border: 1px solid transparent;
        }
        section[data-testid="stSidebar"] div[role="radiogroup"] label:hover {
          background: rgba(59,130,246,0.10);
        }

        /* Active nav item (best-effort across Streamlit/BaseWeb versions) */
        section[data-testid="stSidebar"] label[data-baseweb="radio"][aria-checked="true"],
        section[data-testid="stSidebar"] div[role="radiogroup"] label:has(input:checked) {
          background: rgba(59,130,246,0.14);
          border-color: var(--border-strong);
        }

        /* Subtle motion for charts */
        @keyframes hroFadeUp {
          from { opacity: 0; transform: translateY(4px); }
          to { opacity: 1; transform: translateY(0px); }
        }
        div[data-testid="stPlotlyChart"], div[data-testid="stDataFrame"] {
          animation: hroFadeUp 180ms ease-out;
        }

        /* Responsiveness */
        @media (max-width: 900px) {
          .block-container { padding-left: 1rem; padding-right: 1rem; }
          .hro-page-header { flex-direction: column; align-items:flex-start; }
          .hro-header-meta { text-align:left; }
        }

        </style>
        """,
        unsafe_allow_html=True,
    )

    # Visible indicator so we can confirm the updated UI is actually being rendered.
    st.markdown(
        f"<div class='hro-build-badge'>UI {UI_BUILD_ID}</div>",
        unsafe_allow_html=True,
    )


def page_header(title: str, subtitle: str | None = None, *, meta_right: str | None = None):
    """Premium page header wrapper."""

    st.markdown(
        f"""
        <div class="hro-page-header">
          <div>
            <div class="hro-page-title">{_escape_html(title)}</div>
            {f'<div class="hro-page-subtitle">{_escape_html(subtitle)}</div>' if subtitle else ''}
          </div>
          <div class="hro-header-meta">{_escape_html(meta_right or '')}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def section_header(title: str, subtitle: str | None = None):
    """Consistent section header (visual hierarchy).

    Pure UI wrapper; safe to use broadly.
    """

    st.markdown(
        f"""
        <div class="hro-section">
          <div>
            <div class="hro-section-title">{_escape_html(title)}</div>
            {f'<div class="hro-section-subtitle">{_escape_html(subtitle)}</div>' if subtitle else ''}
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def kpi_card(title, value, delta=None, status="normal"):
    status = str(status or "normal").lower()
    accent = {
        "normal": "hro-accent-normal",
        "info": "hro-accent-normal",
        "success": "hro-accent-success",
        "warning": "hro-accent-warning",
        "critical": "hro-accent-critical",
    }.get(status, "hro-accent-normal")

    st.markdown(
        f"""
        <div class="hro-kpi {accent}">
            <div class="hro-kpi-title">{_escape_html(title)}</div>
            <div class="hro-kpi-value">{_escape_html(str(value))}</div>
            {f'<div class="hro-kpi-delta">{_escape_html(str(delta))}</div>' if delta else ''}
        </div>
        """,
        unsafe_allow_html=True,
    )


def alert_box(message, level="info"):
    level = str(level or "info").lower()
    badge_class = {
        "info": "hro-badge-info",
        "success": "hro-badge-success",
        "warning": "hro-badge-warning",
        "critical": "hro-badge-critical",
    }.get(level, "hro-badge-info")
    label = {
        "info": "INSIGHT",
        "success": "STABLE",
        "warning": "ATTENTION",
        "critical": "CRITICAL",
    }.get(level, "INSIGHT")

    st.markdown(
        f"""
        <div class="hro-alert">
            <div class="hro-alert-title"><span class="hro-badge {badge_class}">{label}</span></div>
            <div class="hro-alert-body">{_escape_html(str(message))}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def status_badge(text: str, tone: str = "neutral"):
    tone = str(tone or "neutral").lower()
    badge_class = {
        "neutral": "hro-badge-neutral",
        "info": "hro-badge-info",
        "success": "hro-badge-success",
        "warning": "hro-badge-warning",
        "critical": "hro-badge-critical",
    }.get(tone, "hro-badge-neutral")
    st.markdown(
        f'<span class="hro-badge {badge_class}">{_escape_html(text)}</span>',
        unsafe_allow_html=True,
    )


# Backwards compatibility for old callers.
def badge(text, color="red"):
    # Map old color usage into tones.
    color = str(color or "").lower()
    if color in {"#ef4444", "red"}:
        return status_badge(str(text), "critical")
    if color in {"#f59e0b", "orange"}:
        return status_badge(str(text), "warning")
    if color in {"#10b981", "green"}:
        return status_badge(str(text), "success")
    if color in {"#3b82f6", "blue", "#2563eb"}:
        return status_badge(str(text), "info")
    return status_badge(str(text), "neutral")


def scoped_key(*parts: object) -> str:
    """Build a stable, deterministic Streamlit key from hierarchical parts."""

    cleaned: list[str] = []
    for part in parts:
        if part is None:
            continue
        text = str(part).strip()
        if not text:
            continue
        text = text.replace(" ", "_")
        text = re.sub(r"[^a-zA-Z0-9_\-]", "_", text)
        text = re.sub(r"_+", "_", text)
        cleaned.append(text)
    return "_".join(cleaned) if cleaned else "key"


def modern_table(df, *, key: str | None = None):
    """Dataframe wrapper with optional Streamlit key for safe reuse."""

    if key:
        st.dataframe(df, use_container_width=True, hide_index=True, key=key)
    else:
        st.dataframe(df, use_container_width=True, hide_index=True)


def empty_state(message="No data available"):
    st.markdown(
        f"""
        <div class="hro-empty">
            <div style="font-size:1.75rem; margin-bottom:8px;">🩺</div>
            <div style="font-weight:800; color: var(--text); opacity:0.82; margin-bottom:6px;">Nothing to show yet</div>
            <div style="color: var(--text-2);">{message}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def sidebar_status_card(title: str, lines: list[str]):
    body = "".join([f"<div style='margin-bottom:6px'>{line}</div>" for line in lines])
    st.sidebar.markdown(
        f"""
        <div style="background:var(--bg-elev); color:var(--text); padding:14px; border-radius:14px; margin-bottom:12px; border:1px solid var(--border); box-shadow:var(--shadow-sm);">
            <div style="font-weight:800; margin-bottom:8px;">{title}</div>
            {body}
        </div>
        """,
        unsafe_allow_html=True,
    )














