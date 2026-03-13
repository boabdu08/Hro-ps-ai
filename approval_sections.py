import streamlit as st
import pandas as pd
from datetime import datetime
import os


LOG_FILE = "recommendation_log.csv"


@st.cache_data
def load_recommendations():
    if not os.path.exists(LOG_FILE):
        df = pd.DataFrame(columns=[
            "recommendation_id",
            "timestamp",
            "type",
            "message",
            "status",
            "approved_by"
        ])
        df.to_csv(LOG_FILE, index=False)
        return df

    return pd.read_csv(LOG_FILE)


def save_recommendations(df):
    df.to_csv(LOG_FILE, index=False)
    load_recommendations.clear()


def generate_ai_recommendations(peak, beds_needed, doctors_needed, emergency_level):
    recommendations = []

    if peak > 120:
        recommendations.append({
            "type": "capacity",
            "message": f"Peak forecast reached {int(peak)} patients. Recommend opening overflow capacity."
        })

    if beds_needed > 120:
        recommendations.append({
            "type": "beds",
            "message": f"Beds needed = {beds_needed}. Recommend reallocating beds or delaying non-urgent admissions."
        })

    if doctors_needed > 15:
        recommendations.append({
            "type": "staff",
            "message": f"Doctors needed = {doctors_needed}. Recommend adding backup doctors to upcoming shifts."
        })

    if emergency_level == "HIGH":
        recommendations.append({
            "type": "emergency",
            "message": "Emergency load is HIGH. Recommend activating emergency surge plan."
        })

    return recommendations


def sync_recommendations(peak, beds_needed, doctors_needed, emergency_level):
    df = load_recommendations()
    generated = generate_ai_recommendations(peak, beds_needed, doctors_needed, emergency_level)

    existing_pending_messages = set(
        df[df["status"] == "pending"]["message"].tolist()
    ) if not df.empty else set()

    new_rows = []

    for i, rec in enumerate(generated, start=1):
        if rec["message"] not in existing_pending_messages:
            new_rows.append({
                "recommendation_id": f"REC-{datetime.now().strftime('%Y%m%d%H%M%S')}-{i}",
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "type": rec["type"],
                "message": rec["message"],
                "status": "pending",
                "approved_by": ""
            })

    if new_rows:
        df = pd.concat([df, pd.DataFrame(new_rows)], ignore_index=True)
        save_recommendations(df)

    return load_recommendations()


def approve_recommendation(recommendation_id, approver_name):
    df = load_recommendations()

    df.loc[df["recommendation_id"] == recommendation_id, "status"] = "approved"
    df.loc[df["recommendation_id"] == recommendation_id, "approved_by"] = approver_name

    save_recommendations(df)


def reject_recommendation(recommendation_id, approver_name):
    df = load_recommendations()

    df.loc[df["recommendation_id"] == recommendation_id, "status"] = "rejected"
    df.loc[df["recommendation_id"] == recommendation_id, "approved_by"] = approver_name

    save_recommendations(df)


def show_admin_approval_panel(peak, beds_needed, doctors_needed, emergency_level, approver_name):
    st.markdown("## ✅ AI Recommendation Approval Center")

    df = sync_recommendations(peak, beds_needed, doctors_needed, emergency_level)

    if df.empty:
        st.info("No recommendations available.")
        return

    pending_df = df[df["status"] == "pending"]
    approved_df = df[df["status"] == "approved"]
    rejected_df = df[df["status"] == "rejected"]

    st.write("### Pending Recommendations")

    if pending_df.empty:
        st.success("No pending recommendations.")
    else:
        for _, row in pending_df.iterrows():
            st.markdown(f"**{row['type'].upper()}** — {row['message']}")
            c1, c2 = st.columns(2)

            with c1:
                if st.button(f"Approve {row['recommendation_id']}", key=f"approve_{row['recommendation_id']}"):
                    approve_recommendation(row["recommendation_id"], approver_name)
                    st.success(f"{row['recommendation_id']} approved")
                    st.rerun()

            with c2:
                if st.button(f"Reject {row['recommendation_id']}", key=f"reject_{row['recommendation_id']}"):
                    reject_recommendation(row["recommendation_id"], approver_name)
                    st.warning(f"{row['recommendation_id']} rejected")
                    st.rerun()

            st.markdown("---")

    st.write("### Approved Decisions")
    if approved_df.empty:
        st.info("No approved decisions yet.")
    else:
        st.dataframe(approved_df, use_container_width=True, hide_index=True)

    st.write("### Rejected Decisions")
    if rejected_df.empty:
        st.info("No rejected decisions yet.")
    else:
        st.dataframe(rejected_df, use_container_width=True, hide_index=True)