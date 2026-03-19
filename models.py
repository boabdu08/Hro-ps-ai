from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint, Index
from sqlalchemy.sql import func
from database import Base


class Tenant(Base):
    """HospitalAccount / Tenant.

    Row-based multi-tenancy (single DB): every tenant-aware record references a
    tenant_id. All API queries MUST be scoped to tenant_id.
    """

    __tablename__ = "tenants"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    slug = Column(String, nullable=False, unique=True, index=True)
    status = Column(String, nullable=False, default="active", index=True)
    subscription_plan = Column(String, nullable=False, default="free", index=True)
    timezone = Column(String, nullable=True)
    country = Column(String, nullable=True)
    default_language = Column(String, nullable=True, default="en")
    is_active = Column(Boolean, nullable=False, default=True, index=True)
    created_at = Column(DateTime, nullable=False, server_default=func.now(), index=True)
    updated_at = Column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())


class PatientFlow(Base):
    __tablename__ = "patients_flow"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=True, index=True)
    datetime = Column(String, nullable=True)
    patients = Column(Float, nullable=False)
    day_of_week = Column(Integer, nullable=True)
    month = Column(Integer, nullable=True)
    is_weekend = Column(Integer, nullable=True)
    holiday = Column(Integer, nullable=True)
    weather = Column(Float, nullable=True)


class Appointment(Base):
    __tablename__ = "appointments"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=True, index=True)
    appointment_id = Column(String, nullable=True)
    department = Column(String, nullable=True)
    doctor = Column(String, nullable=True)
    date = Column(String, nullable=True)
    time_slot = Column(String, nullable=True)
    patient_count = Column(Integer, nullable=True)
    status = Column(String, nullable=True)


class ORBooking(Base):
    __tablename__ = "or_bookings"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=True, index=True)
    booking_id = Column(String, nullable=True)
    room = Column(String, nullable=True)
    doctor = Column(String, nullable=True)
    department = Column(String, nullable=True)
    date = Column(String, nullable=True)
    time_slot = Column(String, nullable=True)
    procedure = Column(String, nullable=True)
    status = Column(String, nullable=True)


class StaffShift(Base):
    __tablename__ = "staff_shifts"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=True, index=True)
    staff_username = Column(String, nullable=True)
    name = Column(String, nullable=True)
    role = Column(String, nullable=True)
    department = Column(String, nullable=True)
    shift_date = Column(String, nullable=True)
    shift_type = Column(String, nullable=True)
    status = Column(String, nullable=True)


class User(Base):
    __tablename__ = "users"

    __table_args__ = (
        # SaaS-ready: username uniqueness should be per tenant.
        # Note: existing DB may still have a global unique constraint on username;
        # migrations will move toward tenant-scoped uniqueness.
        UniqueConstraint("tenant_id", "username", name="uq_users_tenant_username"),
        Index("ix_users_tenant_role", "tenant_id", "role"),
        Index("ix_users_tenant_dept", "tenant_id", "department"),
    )

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=True, index=True)
    username = Column(String, nullable=False)
    name = Column(String, nullable=True)
    role = Column(String, nullable=True)
    department = Column(String, nullable=True)
    password = Column(String, nullable=False)


class MessageLog(Base):
    __tablename__ = "message_log"

    __table_args__ = (
        # Keep message_id globally unique for safety and to keep FK references valid.
        # Tenant isolation is enforced at query layer.
        Index("ix_message_log_tenant_created", "tenant_id", "created_at"),
    )

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=True, index=True)
    message_id = Column(String, unique=True, nullable=False, index=True)
    # Legacy: originally stored as string. Keep for backward compatibility.
    timestamp = Column(String, nullable=False)

    # Production-friendly lifecycle fields.
    created_at = Column(DateTime, nullable=True, index=True)
    # Use "message_type" instead of "type" (reserved in Python).
    # Values: normal | alert | critical | decision
    message_type = Column(String, nullable=False, default="normal", index=True)
    # Pinned messages never auto-archive.
    is_pinned = Column(Boolean, nullable=False, default=False, index=True)

    sender_role = Column(String, nullable=False)
    sender_name = Column(String, nullable=False)

    target_role = Column(String, nullable=False, default="all")
    target_department = Column(String, nullable=False, default="All Departments")

    priority = Column(String, nullable=False, default="normal")
    category = Column(String, nullable=False, default="general")
    title = Column(String, nullable=False)
    message = Column(Text, nullable=False)

    status = Column(String, nullable=False, default="sent")

    reply = Column(Text, nullable=True)
    reply_by = Column(String, nullable=True)
    reply_timestamp = Column(String, nullable=True)

    # Legacy/global fields (deprecated for per-user state but kept to avoid breaking DB rows).
    acknowledged = Column(String, nullable=False, default="no")
    archived = Column(Boolean, nullable=False, default=False)


class MessageRead(Base):
    """Per-user state for a message (read + personal archive/hide).

    Required by product behavior:
    - read/unread must be per user
    - a user can hide/archive a message without affecting other users
    """

    __tablename__ = "message_reads"
    __table_args__ = (
        UniqueConstraint("tenant_id", "message_id", "user_id", name="uq_message_reads_tenant_message_user"),
        Index("ix_message_reads_tenant_user_read", "tenant_id", "user_id", "is_read"),
        Index("ix_message_reads_tenant_user_archived", "tenant_id", "user_id", "is_archived"),
    )

    id = Column(Integer, primary_key=True, index=True)

    tenant_id = Column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=True, index=True)

    # We reference MessageLog.message_id (a stable external id) instead of MessageLog.id.
    message_id = Column(String, ForeignKey("message_log.message_id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    is_read = Column(Boolean, nullable=False, default=False)
    read_at = Column(DateTime, nullable=True)

    # Personal archive/hide (does not affect other users).
    is_archived = Column(Boolean, nullable=False, default=False)
    archived_at = Column(DateTime, nullable=True)

    updated_at = Column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())


class RecommendationRecord(Base):
    __tablename__ = "recommendation_records"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=True, index=True)
    recommendation_id = Column(String, unique=True, nullable=False, index=True)
    timestamp = Column(String, nullable=False)
    rec_type = Column(String, nullable=False)
    message = Column(Text, nullable=False)
    status = Column(String, nullable=False, default="pending")
    approved_by = Column(String, nullable=True)
    execution_status = Column(String, nullable=True)
    execution_note = Column(Text, nullable=True)
    affected_entities = Column(Text, nullable=True)


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=True, index=True)
    audit_id = Column(String, unique=True, nullable=False, index=True)
    timestamp = Column(String, nullable=False)
    action = Column(String, nullable=False)
    actor = Column(String, nullable=True)
    target = Column(String, nullable=True)
    status = Column(String, nullable=False)
    details = Column(Text, nullable=True)


class OptimizationRun(Base):
    """Persisted optimization results.

    This is a DB-first record of the optimizer output so we can:
    - support audits (what plan was generated for what forecast)
    - drive approvals from optimizer outputs
    - track outcomes and model/optimizer drift over time

    Note: JSON is stored as Text for portability; in production prefer JSONB.
    """

    __tablename__ = "optimization_runs"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=True, index=True)
    run_id = Column(String, unique=True, nullable=False, index=True)
    timestamp = Column(String, nullable=False)

    predicted_patients = Column(Float, nullable=False)
    objective = Column(Float, nullable=True)

    summary_json = Column(Text, nullable=True)
    allocations_json = Column(Text, nullable=True)
    actions_json = Column(Text, nullable=True)
    recommendations_json = Column(Text, nullable=True)


class Alert(Base):
    """Operational alert generated by rules/AI signals.

    This is separate from MessageLog.
    - Alerts are condition-driven and lifecycle-managed (active/ack/resolved)
    - Messages are communications between users
    """

    __tablename__ = "alerts"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=True, index=True)
    alert_id = Column(String, unique=True, nullable=False, index=True)

    title = Column(String, nullable=False)
    message = Column(Text, nullable=False)

    # capacity_alert | staffing_alert | forecast_alert | optimization_alert | critical_alert | operational_alert
    alert_type = Column(String, nullable=False, default="operational_alert", index=True)
    # low | medium | high | critical
    priority = Column(String, nullable=False, default="medium", index=True)

    source = Column(String, nullable=False, default="system", index=True)
    related_department = Column(String, nullable=True, index=True)

    related_entity_type = Column(String, nullable=True)
    related_entity_id = Column(String, nullable=True)

    created_at = Column(DateTime, nullable=False, server_default=func.now(), index=True)
    expires_at = Column(DateTime, nullable=True, index=True)

    is_active = Column(Boolean, nullable=False, default=True, index=True)

    # Acknowledgement is per-user tracked via notifications, but we keep an overall flag too.
    is_acknowledged = Column(Boolean, nullable=False, default=False, index=True)
    acknowledged_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    acknowledged_at = Column(DateTime, nullable=True)

    resolved_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    resolved_at = Column(DateTime, nullable=True)

    generated_by_rule = Column(String, nullable=True, index=True)
    recommendation_summary = Column(Text, nullable=True)


class NotificationPreference(Base):
    __tablename__ = "notification_preferences"
    __table_args__ = (
        UniqueConstraint("user_id", name="uq_notification_preferences_user"),
        Index("ix_notification_preferences_tenant_user", "tenant_id", "user_id"),
    )

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    receive_in_app = Column(Boolean, nullable=False, default=True)
    receive_email = Column(Boolean, nullable=False, default=False)
    receive_sms = Column(Boolean, nullable=False, default=False)
    receive_push = Column(Boolean, nullable=False, default=False)
    critical_only = Column(Boolean, nullable=False, default=False)

    quiet_hours_start = Column(String, nullable=True)
    quiet_hours_end = Column(String, nullable=True)

    updated_at = Column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())


class Notification(Base):
    """Notification delivery unit.

    For now we implement in-app notifications. Email/SMS/push are future-ready.
    """

    __tablename__ = "notifications"
    __table_args__ = (
        Index("ix_notifications_tenant_user_status", "tenant_id", "user_id", "status"),
        Index("ix_notifications_tenant_user_read", "tenant_id", "user_id", "read_at"),
    )

    id = Column(Integer, primary_key=True, index=True)
    notification_id = Column(String, unique=True, nullable=False, index=True)

    tenant_id = Column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=True, index=True)

    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    alert_id = Column(Integer, ForeignKey("alerts.id", ondelete="SET NULL"), nullable=True, index=True)
    message_id = Column(String, ForeignKey("message_log.message_id", ondelete="SET NULL"), nullable=True, index=True)

    # in_app | email | sms | push
    channel = Column(String, nullable=False, default="in_app", index=True)

    title = Column(String, nullable=False)
    body = Column(Text, nullable=False)

    # pending | queued | sent | delivered | failed | read
    status = Column(String, nullable=False, default="delivered", index=True)

    created_at = Column(DateTime, nullable=False, server_default=func.now(), index=True)
    sent_at = Column(DateTime, nullable=True)
    delivered_at = Column(DateTime, nullable=True)
    read_at = Column(DateTime, nullable=True)

    failure_reason = Column(Text, nullable=True)
    retry_count = Column(Integer, nullable=False, default=0)