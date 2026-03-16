import os
from datetime import datetime, timedelta

import pandas as pd
import streamlit as st

LOG_FILE = "recommendation_log.csv"
SHIFTS_FILE = "shifts.csv"
OR_FILE = "or_bookings.csv"
APPOINTMENTS_FILE = "appointments.csv"

REQUIRED_LOG_COLS = [
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


# ========================================
# HELPERS
# ========================================
def ensure_log_schema(df: pd.DataFrame) -> pd.DataFrame:
    for col in REQUIRED_LOG_COLS:
        if col not in df.columns:
            df[col] = ""
    return df[REQUIRED_LOG_COLS].copy()


def load_recommendations() -> pd.DataFrame:
    if not os.path.exists(LOG_FILE):
        df = pd.DataFrame(columns=REQUIRED_LOG_COLS)
        df.to_csv(LOG_FILE, index=False)
        return df

    df = pd.read_csv(LOG_FILE)
    return ensure_log_schema(df)


def save_recommendations(df: pd.DataFrame):
    df = ensure_log_schema(df)
    df.to_csv(LOG_FILE, index=False)


def reset_recommendations():
    pd.DataFrame(columns=REQUIRED_LOG_COLS).to_csv(LOG_FILE, index=False)


def load_csv_or_empty(path, columns):
    if not os.path.exists(path):
        df = pd.DataFrame(columns=columns)
        df.to_csv(path, index=False)
        return df

    df = pd.read_csv(path)
    for col in columns:
        if col not in df.columns:
            df[col] = ""
    return df[columns].copy()


def save_csv(df, path):
    df.to_csv(path, index=False)


def infer_department_from_message(message: str):
    message_lower = str(message).lower()

    if "icu" in message_lower:
        return "ICU"
    if "general ward" in message_lower:
        return "General Ward"
    if "surgery" in message_lower:
        return "Surgery"
    if "radiology" in message_lower:
        return "Radiology"

    return "ER"


def create_recommendation_row(rec_type: str, message: str):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    rec_id = f"REC-{datetime.now().strftime('%Y%m%d%H%M%S%f')}"
    return {
        "recommendation_id": rec_id,
        "timestamp": ts,
        "type": rec_type,
        "message": message,
        "status": "pending",
        "approved_by": "",
        "execution_status": "",
        "execution_note": "",
        "affected_files": ""
    }


def add_recommendations_if_missing(df: pd.DataFrame, rows_to_add: list[dict]) -> pd.DataFrame:
    existing_messages = set(df["message"].astype(str).tolist()) if not df.empty else set()

    new_rows = []
    for row in rows_to_add:
        if row["message"] not in existing_messages:
            new_rows.append(row)

    if new_rows:
        df = pd.concat([df, pd.DataFrame(new_rows)], ignore_index=True)

    return df


# ========================================
# RECOMMENDATION GENERATION
# ========================================
def generate_ai_recommendations(peak, beds_needed, doctors_needed, emergency_level):
    recommendations = []

    if peak >= 100:
        recommendations.append({
            "type": "capacity",
            "message": f"Peak forecast reached {int(peak)} patients. Recommend opening overflow capacity."
        })

    if beds_needed >= 100:
        recommendations.append({
            "type": "beds",
            "message": f"Beds needed = {beds_needed}. Recommend reallocating beds or delaying non-urgent admissions."
        })

    if doctors_needed >= 12:
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

    pending_messages = set(
        df[df["status"] == "pending"]["message"].astype(str).tolist()
    ) if not df.empty else set()

    rows = []
    for rec in generated:
        if rec["message"] not in pending_messages:
            rows.append(create_recommendation_row(rec["type"], rec["message"]))

    if rows:
        df = pd.concat([df, pd.DataFrame(rows)], ignore_index=True)
        save_recommendations(df)

    return load_recommendations()


def seed_demo_recommendations():
    df = load_recommendations()

    demo_rows = [
        create_recommendation_row(
            "capacity",
            "Peak forecast reached 135 patients. Recommend opening overflow capacity."
        ),
        create_recommendation_row(
            "beds",
            "Beds needed = 145. Recommend reallocating beds or delaying non-urgent admissions."
        ),
        create_recommendation_row(
            "staff",
            "Doctors needed = 18. Recommend adding backup doctors to upcoming shifts."
        ),
        create_recommendation_row(
            "emergency",
            "Emergency load is HIGH. Recommend activating emergency surge plan."
        ),
    ]

    df = add_recommendations_if_missing(df, demo_rows)
    save_recommendations(df)


# ========================================
# EXECUTION LAYER
# ========================================
def execute_staff_decision(message):
    shifts_cols = ["staff_username", "name", "role", "department", "shift_date", "shift_type", "status"]
    shifts_df = load_csv_or_empty(SHIFTS_FILE, shifts_cols)

    department = infer_department_from_message(message)
    next_day = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")

    new_shift = pd.DataFrame([{
        "staff_username": "backup_doctor",
        "name": "Backup Doctor",
        "role": "doctor",
        "department": department,
        "shift_date": next_day,
        "shift_type": "Emergency Backup",
        "status": "Auto-Assigned"
    }])

    shifts_df = pd.concat([shifts_df, new_shift], ignore_index=True)
    save_csv(shifts_df, SHIFTS_FILE)

    return "executed", f"Added backup doctor shift in {department} for {next_day}.", SHIFTS_FILE


def execute_beds_decision(message):
    appointments_cols = ["appointment_id", "department", "doctor", "date", "time_slot", "patient_count", "status"]
    appointments_df = load_csv_or_empty(APPOINTMENTS_FILE, appointments_cols)

    if appointments_df.empty:
        return "skipped", "No appointments found to rebalance.", APPOINTMENTS_FILE

    appointments_df["patient_count"] = pd.to_numeric(
        appointments_df["patient_count"], errors="coerce"
    ).fillna(0)

    busiest_idx = appointments_df["patient_count"].idxmax()
    appointments_df.loc[busiest_idx, "status"] = "Review Required"

    save_csv(appointments_df, APPOINTMENTS_FILE)

    row = appointments_df.loc[busiest_idx]
    return "executed", f"Marked appointment slot {row['time_slot']} in {row['department']} as Review Required.", APPOINTMENTS_FILE


def execute_capacity_decision(message):
    appointments_cols = ["appointment_id", "department", "doctor", "date", "time_slot", "patient_count", "status"]
    appointments_df = load_csv_or_empty(APPOINTMENTS_FILE, appointments_cols)

    if appointments_df.empty:
        return "skipped", "No appointment slots available for capacity reallocation.", APPOINTMENTS_FILE

    appointments_df["patient_count"] = pd.to_numeric(
        appointments_df["patient_count"], errors="coerce"
    ).fillna(0)

    top_two = appointments_df.sort_values(by="patient_count", ascending=False).head(2).index
    appointments_df.loc[top_two, "status"] = "Reschedule Suggested"

    save_csv(appointments_df, APPOINTMENTS_FILE)

    return "executed", "Marked top pressure appointment slots as Reschedule Suggested.", APPOINTMENTS_FILE


def execute_emergency_decision(message):
    or_cols = ["booking_id", "room", "doctor", "department", "date", "time_slot", "procedure", "status"]
    appointments_cols = ["appointment_id", "department", "doctor", "date", "time_slot", "patient_count", "status"]

    or_df = load_csv_or_empty(OR_FILE, or_cols)
    appt_df = load_csv_or_empty(APPOINTMENTS_FILE, appointments_cols)

    note_parts = []
    affected_files = []

    if not or_df.empty:
        pending_mask = or_df["status"].astype(str).str.lower() == "pending"
        if pending_mask.any():
            or_df.loc[pending_mask, "status"] = "Priority Review"
            save_csv(or_df, OR_FILE)
            note_parts.append("Pending OR bookings escalated to Priority Review")
            affected_files.append(OR_FILE)

    if not appt_df.empty:
        appt_df["patient_count"] = pd.to_numeric(
            appt_df["patient_count"], errors="coerce"
        ).fillna(0)

        busiest_idx = appt_df["patient_count"].idxmax()
        appt_df.loc[busiest_idx, "status"] = "Restricted Intake"
        save_csv(appt_df, APPOINTMENTS_FILE)

        row = appt_df.loc[busiest_idx]
        note_parts.append(
            f"Appointment slot {row['time_slot']} in {row['department']} set to Restricted Intake"
        )
        affected_files.append(APPOINTMENTS_FILE)

    if not note_parts:
        return "skipped", "No OR bookings or appointments available for emergency actions.", ""

    return "executed", " | ".join(note_parts), ", ".join(affected_files)


def execute_decision(decision_type, message):
    if decision_type == "staff":
        return execute_staff_decision(message)
    if decision_type == "beds":
        return execute_beds_decision(message)
    if decision_type == "capacity":
        return execute_capacity_decision(message)
    if decision_type == "emergency":
        return execute_emergency_decision(message)

    return "skipped", "No execution rule defined for this recommendation type.", ""


# ========================================
# APPROVE / REJECT
# ========================================
def approve_recommendation(recommendation_id, approver_name):
    df = load_recommendations()

    row_mask = df["recommendation_id"] == recommendation_id
    if not row_mask.any():
        return False

    row = df[row_mask].iloc[0]

    execution_status, execution_note, affected_files = execute_decision(
        decision_type=row["type"],
        message=row["message"]
    )

    df.loc[row_mask, "status"] = "approved"
    df.loc[row_mask, "approved_by"] = approver_name
    df.loc[row_mask, "execution_status"] = execution_status
    df.loc[row_mask, "execution_note"] = execution_note
    df.loc[row_mask, "affected_files"] = affected_files

    save_recommendations(df)
    return True


def reject_recommendation(recommendation_id, approver_name):
    df = load_recommendations()

    row_mask = df["recommendation_id"] == recommendation_id
    if not row_mask.any():
        return False

    df.loc[row_mask, "status"] = "rejected"
    df.loc[row_mask, "approved_by"] = approver_name
    df.loc[row_mask, "execution_status"] = "not_executed"
    df.loc[row_mask, "execution_note"] = "Recommendation rejected by manager."
    df.loc[row_mask, "affected_files"] = ""

    save_recommendations(df)
    return True


# ========================================
# UI PANEL
# ========================================
def show_admin_approval_panel(peak, beds_needed, doctors_needed, emergency_level, approver_name):
    st.markdown("## ✅ AI Recommendation Approval Center")

    top1, top2, top3 = st.columns(3)

    with top1:
        if st.button("Generate Demo Recommendations"):
            seed_demo_recommendations()
            st.success("Demo recommendations generated.")
            st.rerun()

    with top2:
        if st.button("Reset Recommendation Log"):
            reset_recommendations()
            st.warning("Recommendation log reset.")
            st.rerun()

    with top3:
        st.metric("Current Emergency Level", str(emergency_level))

    st.markdown("---")

    df = sync_recommendations(peak, beds_needed, doctors_needed, emergency_level)

    if df.empty:
        st.info("No recommendations available.")
        return

    pending_df = df[df["status"] == "pending"].copy()
    approved_df = df[df["status"] == "approved"].copy()
    rejected_df = df[df["status"] == "rejected"].copy()

    s1, s2, s3 = st.columns(3)
    s1.metric("Pending", len(pending_df))
    s2.metric("Approved", len(approved_df))
    s3.metric("Rejected", len(rejected_df))

    st.write("### Pending Recommendations")

    if pending_df.empty:
        st.success("No pending recommendations.")
    else:
        pending_df = pending_df.sort_values(by="timestamp", ascending=False)

        for _, row in pending_df.iterrows():
            st.markdown(f"**{str(row['type']).upper()}** — {row['message']}")
            st.caption(f"Created at: {row['timestamp']}")

            c1, c2 = st.columns(2)

            with c1:
                if st.button(
                    f"Approve {row['recommendation_id']}",
                    key=f"approve_{row['recommendation_id']}"
                ):
                    ok = approve_recommendation(row["recommendation_id"], approver_name)
                    if ok:
                        st.success(f"{row['recommendation_id']} approved and executed")
                    else:
                        st.error("Failed to approve recommendation.")
                    st.rerun()

            with c2:
                if st.button(
                    f"Reject {row['recommendation_id']}",
                    key=f"reject_{row['recommendation_id']}"
                ):
                    ok = reject_recommendation(row["recommendation_id"], approver_name)
                    if ok:
                        st.warning(f"{row['recommendation_id']} rejected")
                    else:
                        st.error("Failed to reject recommendation.")
                    st.rerun()

            st.markdown("---")

    st.write("### Approved Decisions")
    if approved_df.empty:
        st.info("No approved decisions yet.")
    else:
        approved_df = approved_df.sort_values(by="timestamp", ascending=False)
        st.dataframe(approved_df, use_container_width=True, hide_index=True)

    st.write("### Rejected Decisions")
    if rejected_df.empty:
        st.info("No rejected decisions yet.")
    else:
        rejected_df = rejected_df.sort_values(by="timestamp", ascending=False)
        st.dataframe(rejected_df, use_container_width=True, hide_index=True)