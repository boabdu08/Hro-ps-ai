from __future__ import annotations

import re
import streamlit as st


# ------------------------------
# Premium design system (tokens)
# ------------------------------


THEME = {
    # Unique hybrid canvas (not pure white, not dark)
    "bg": "#EEF0FF",
    "bg_2": "#EEF7FF",
    "bg_3": "#F3EEFF",

    # Glass-like floating surfaces
    "surface": "rgba(255, 255, 255, 0.72)",
    "surface_solid": "#F8F9FF",
    "surface_2": "rgba(255, 255, 255, 0.55)",

    "text": "#0B1020",
    "muted": "#51607A",
    "border": "rgba(15, 23, 42, 0.10)",
    "border_strong": "rgba(91, 92, 255, 0.22)",

    "shadow": "0 18px 45px rgba(15, 23, 42, 0.10)",
    "shadow_sm": "0 10px 26px rgba(15, 23, 42, 0.10)",

    "radius": "18px",
    "radius_sm": "14px",

    # Brand colors
    "primary": "#5B5CFF",       # blue‑violet
    "primary_2": "#3E3BFF",
    "accent_teal": "#22D3EE",

    # Status
    "success": "#2DD4BF",
    "warning": "#FBBF24",
    "critical": "#FB7185",
    "info": "#60A5FA",
}


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
    st.markdown(
        """
        <style>
        /* ------------------------------
           Global premium identity shell
           ------------------------------ */

        /* Canvas gradient (unique identity) */
        .stApp {
            background:
              radial-gradient(1200px 520px at 15% 10%, rgba(91,92,255,0.18), rgba(91,92,255,0.00) 60%),
              radial-gradient(900px 420px at 90% 20%, rgba(34,211,238,0.14), rgba(34,211,238,0.00) 65%),
              radial-gradient(900px 520px at 35% 95%, rgba(168,85,247,0.10), rgba(168,85,247,0.00) 55%),
              linear-gradient(180deg, """ + THEME["bg"] + """ 0%, """ + THEME["bg_2"] + """ 40%, """ + THEME["bg_3"] + """ 100%);
        }

        /* App spacing */
        .main {padding-top: 0.25rem;}
        .block-container {padding-top: 1.2rem; padding-bottom: 2.5rem; max-width: 1280px;}

        /* Base typography polish */
        html, body, [class*="css"]  {
            font-feature-settings: "kern" 1, "liga" 1;
            -webkit-font-smoothing: antialiased;
            text-rendering: optimizeLegibility;
        }

        /* Card system (glass surfaces) */
        .hro-surface {
            background: """ + THEME["surface"] + """;
            border: 1px solid """ + THEME["border"] + """;
            border-radius: """ + THEME["radius"] + """;
            box-shadow: """ + THEME["shadow"] + """;
            backdrop-filter: blur(14px);
            -webkit-backdrop-filter: blur(14px);
        }

        .hro-surface-sm {
            background: """ + THEME["surface_2"] + """;
            border: 1px solid """ + THEME["border"] + """;
            border-radius: """ + THEME["radius_sm"] + """;
            box-shadow: """ + THEME["shadow_sm"] + """;
            backdrop-filter: blur(12px);
            -webkit-backdrop-filter: blur(12px);
        }

        .hro-page-header {
            display:flex; justify-content:space-between; align-items:flex-end;
            gap: 12px;
            padding: 18px 18px;
            margin-bottom: 14px;
            background:
                linear-gradient(135deg, rgba(91,92,255,0.16), rgba(34,211,238,0.10));
            border: 1px solid """ + THEME["border_strong"] + """;
            border-radius: 18px;
            box-shadow: """ + THEME["shadow_sm"] + """;
            backdrop-filter: blur(14px);
            -webkit-backdrop-filter: blur(14px);
        }

        .hro-page-title {
            font-size: 1.5rem;
            font-weight: 750;
            letter-spacing: -0.02em;
            color: """ + THEME["text"] + """;
            margin: 0;
        }

        .hro-page-subtitle {
            color: """ + THEME["muted"] + """;
            margin-top: 0.35rem;
            font-size: 0.95rem;
        }

        .hro-header-meta {
            text-align: right;
            color: """ + THEME["muted"] + """;
            font-size: 0.9rem;
        }

        /* KPI card */
        .hro-kpi {
            padding: 16px 16px;
            border-radius: 18px;
            background: """ + THEME["surface"] + """;
            border: 1px solid """ + THEME["border"] + """;
            box-shadow: """ + THEME["shadow_sm"] + """;
            min-height: 110px;
            backdrop-filter: blur(14px);
            -webkit-backdrop-filter: blur(14px);
            transition: transform 140ms ease, box-shadow 140ms ease, border-color 140ms ease;
        }
        .hro-kpi:hover {
            transform: translateY(-2px);
            box-shadow: 0 22px 52px rgba(15, 23, 42, 0.14);
            border-color: rgba(91,92,255,0.22);
        }
        .hro-kpi-title {
            color: """ + THEME["muted"] + """;
            font-size: 0.9rem;
            margin-bottom: 6px;
            font-weight: 600;
        }
        .hro-kpi-value {
            color: """ + THEME["text"] + """;
            font-size: 2.05rem;
            font-weight: 800;
            letter-spacing: -0.03em;
            line-height: 1.15;
        }
        .hro-kpi-delta {
            margin-top: 8px;
            color: """ + THEME["muted"] + """;
            font-size: 0.9rem;
        }

        /* Status accent line */
        .hro-accent-normal {border-left: 6px solid rgba(91,92,255,0.85);}
        .hro-accent-success {border-left: 6px solid rgba(45,212,191,0.85);}
        .hro-accent-warning {border-left: 6px solid rgba(251,191,36,0.90);}
        .hro-accent-critical {border-left: 6px solid rgba(251,113,133,0.92);}

        /* Badges */
        .hro-badge {
            display:inline-flex;
            align-items:center;
            gap: 6px;
            padding: 4px 10px;
            border-radius: 999px;
            font-size: 12px;
            font-weight: 700;
            letter-spacing: 0.02em;
            border: 1px solid rgba(0,0,0,0.06);
        }
        .hro-badge-neutral {background: rgba(2, 6, 23, 0.06); color: """ + THEME["text"] + """;}
        .hro-badge-info {background: rgba(91,92,255,0.14); color: #2b2c7f; border-color: rgba(91,92,255,0.25);}
        .hro-badge-success {background: rgba(45,212,191,0.16); color: #115e59; border-color: rgba(45,212,191,0.30);}
        .hro-badge-warning {background: rgba(251,191,36,0.18); color: #78350f; border-color: rgba(251,191,36,0.34);}
        .hro-badge-critical {background: rgba(251,113,133,0.16); color: #881337; border-color: rgba(251,113,133,0.30);}

        /* Alert cards */
        .hro-alert {
            padding: 14px 14px;
            border-radius: 16px;
            background: """ + THEME["surface"] + """;
            border: 1px solid """ + THEME["border"] + """;
            box-shadow: """ + THEME["shadow_sm"] + """;
            backdrop-filter: blur(14px);
            -webkit-backdrop-filter: blur(14px);
        }
        .hro-alert-title {font-weight: 800; margin: 0 0 4px 0;}
        .hro-alert-body {color: """ + THEME["text"] + """; opacity: 0.92;}
        .hro-alert-meta {margin-top: 8px; color: """ + THEME["muted"] + """; font-size: 0.88rem;}

        /* Empty states */
        .hro-empty {
            text-align:center;
            padding: 38px 18px;
            border: 1px dashed rgba(148, 163, 184, 0.6);
            border-radius: 18px;
            background: rgba(255,255,255,0.5);
            color: """ + THEME["muted"] + """;
        }

        /* Streamlit native component polish */
        /* Inputs */
        div[data-baseweb="input"] > div,
        div[data-baseweb="textarea"] > div,
        div[data-baseweb="select"] > div {
            border-radius: 14px !important;
            border: 1px solid """ + THEME["border"] + """ !important;
            background: rgba(255,255,255,0.70) !important;
            box-shadow: none !important;
            backdrop-filter: blur(10px);
        }

        /* Buttons */
        .stButton > button {
            border-radius: 14px !important;
            border: 1px solid rgba(91,92,255,0.25) !important;
            padding: 0.55rem 0.85rem !important;
            font-weight: 700 !important;
            transition: transform 140ms ease, box-shadow 140ms ease;
        }
        .stButton > button:hover {
            transform: translateY(-1px);
            box-shadow: 0 14px 32px rgba(15, 23, 42, 0.14);
        }

        /* Tabs */
        .stTabs [data-baseweb="tab"] {
            font-weight: 700 !important;
        }

        /* Dataframe container */
        div[data-testid="stDataFrame"] {
            border-radius: 16px;
            overflow: hidden;
            border: 1px solid """ + THEME["border"] + """;
        }

        /* Sidebar refinement */
        section[data-testid="stSidebar"] {
            background:
              linear-gradient(180deg, rgba(255,255,255,0.55), rgba(255,255,255,0.35));
            border-right: 1px solid rgba(15,23,42,0.08);
            backdrop-filter: blur(16px);
            -webkit-backdrop-filter: blur(16px);
        }
        </style>
        """,
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
    # Keep compatibility with existing calls, but use a more premium layout.
    st.markdown(f"### {title}")
    if subtitle:
        st.caption(subtitle)


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
            <div class="hro-alert-body">{message}</div>
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
            <div style="font-size:2rem; margin-bottom:8px;">📭</div>
            <div style="font-weight:700; color: {THEME['text']}; opacity:0.75; margin-bottom:6px;">No items yet</div>
            <div>{message}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def sidebar_status_card(title: str, lines: list[str]):
    body = "".join([f"<div style='margin-bottom:6px'>{line}</div>" for line in lines])
    st.sidebar.markdown(
        f"""
        <div style="background:{THEME['surface']}; color:{THEME['text']}; padding:14px; border-radius:14px; margin-bottom:12px; border:1px solid {THEME['border']}; box-shadow:{THEME['shadow_sm']};">
            <div style="font-weight:800; margin-bottom:8px;">{title}</div>
            {body}
        </div>
        """,
        unsafe_allow_html=True,
    )







