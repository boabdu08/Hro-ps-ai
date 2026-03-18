import streamlit as st


def inject_base_styles():
    st.markdown(
        """
        <style>
        .main {padding-top: 0.5rem;}
        .block-container {padding-top: 1rem; padding-bottom: 2rem;}
        .hro-header {
            display:flex; justify-content:space-between; align-items:center;
            padding:16px 18px; border-radius:14px; background:#111827; color:white;
            margin-bottom:14px; border:1px solid rgba(255,255,255,0.06);
        }
        .hro-card {
            padding:16px; border-radius:14px; color:white; min-height:120px;
            box-shadow: 0 6px 18px rgba(0,0,0,0.12);
        }
        .hro-badge {
            display:inline-block; padding:4px 10px; border-radius:999px; color:white;
            font-size:12px; font-weight:600;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def section_header(title: str, subtitle: str | None = None):
    st.markdown(f"## {title}")
    if subtitle:
        st.caption(subtitle)


def kpi_card(title, value, delta=None, status="normal"):
    color = {
        "normal": "#1f2937",
        "warning": "#f59e0b",
        "critical": "#ef4444",
    }.get(status, "#1f2937")
    delta_html = f"<p style='margin:0; opacity:0.9;'>{delta}</p>" if delta else ""
    st.markdown(
        f"""
        <div class="hro-card" style="background:{color};">
            <div style="font-size:0.95rem; opacity:0.9;">{title}</div>
            <div style="font-size:2rem; font-weight:700; margin:6px 0 8px 0;">{value}</div>
            {delta_html}
        </div>
        """,
        unsafe_allow_html=True,
    )


def alert_box(message, level="info"):
    colors = {"info": "#3b82f6", "warning": "#f59e0b", "critical": "#ef4444", "success": "#10b981"}
    st.markdown(
        f"""
        <div style="background:{colors.get(level, '#3b82f6')}; padding:14px; border-radius:12px; color:white; margin-bottom:10px;">
            {message}
        </div>
        """,
        unsafe_allow_html=True,
    )


def badge(text, color="red"):
    st.markdown(
        f'<span class="hro-badge" style="background:{color};">{text}</span>',
        unsafe_allow_html=True,
    )


def modern_table(df):
    st.dataframe(df, use_container_width=True, hide_index=True)


def empty_state(message="No data available"):
    st.markdown(
        f"""
        <div style="text-align:center; padding:36px; color:#9ca3af; border:1px dashed #334155; border-radius:12px;">
            <div style="font-size:2rem; margin-bottom:8px;">📭</div>
            <div>{message}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def sidebar_status_card(title: str, lines: list[str]):
    body = "".join([f"<div style='margin-bottom:6px'>{line}</div>" for line in lines])
    st.sidebar.markdown(
        f"""
        <div style="background:#111827; color:white; padding:14px; border-radius:12px; margin-bottom:12px;">
            <div style="font-weight:700; margin-bottom:8px;">{title}</div>
            {body}
        </div>
        """,
        unsafe_allow_html=True,
    )

