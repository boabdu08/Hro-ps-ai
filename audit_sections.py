import os
import pandas as pd
import streamlit as st

LOG_FILE = "recommendation_log.csv"

EXPECTED_COLS = [
    "recommendation_id",
    "timestamp",
    "type",
    "message",
    "status",
    "approved_by",
    "execution_status",
    "execution_note",
    "affected_files"
]


def load_audit_log():
    if not os.path.exists(LOG_FILE):
        return pd.DataFrame(columns=EXPECTED_COLS)

    df = pd.read_csv(LOG_FILE)

    for col in EXPECTED_COLS:
        if col not in df.columns:
            df[col] = ""

    return df[EXPECTED_COLS].copy()


def show_audit_summary():
    st.markdown("## 🧾 Audit Summary")

    df = load_audit_log()

    if df.empty:
        st.info("No audit records available.")
        return

    total = len(df)
    approved = len(df[df["status"] == "approved"])
    rejected = len(df[df["status"] == "rejected"])
    executed = len(df[df["execution_status"] == "executed"])

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total Decisions", total)
    c2.metric("Approved", approved)
    c3.metric("Rejected", rejected)
    c4.metric("Executed", executed)


def show_audit_table():
    st.markdown("## 📚 Decision Audit Log")

    df = load_audit_log()

    if df.empty:
        st.info("No audit log records available.")
        return

    df = df.sort_values(by="timestamp", ascending=False)
    st.dataframe(df, use_container_width=True, hide_index=True)


def show_execution_trace():
    st.markdown("## 🛠 Execution Trace")

    df = load_audit_log()

    if df.empty:
        st.info("No execution trace available.")
        return

    executed_df = df[df["execution_status"] == "executed"].copy()

    if executed_df.empty:
        st.info("No executed decisions yet.")
        return

    executed_df = executed_df.sort_values(by="timestamp", ascending=False)

    for _, row in executed_df.iterrows():
        st.success(f"{row['recommendation_id']} — {str(row['type']).upper()}")
        st.write(f"**Message:** {row['message']}")
        st.write(f"**Approved By:** {row['approved_by']}")
        st.write(f"**Execution Note:** {row['execution_note']}")
        st.write(f"**Affected Files:** {row['affected_files']}")
        st.caption(f"Timestamp: {row['timestamp']}")
        st.markdown("---")