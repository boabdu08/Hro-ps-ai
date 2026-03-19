"""Very small, repo-friendly DB migration helpers.

This project currently uses `Base.metadata.create_all()` (no Alembic). That won't
add new columns or create indexes in existing tables.

To keep changes safe and incremental, we apply a few idempotent migrations on
startup.

In production you should move this to Alembic migrations.
"""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.engine import Engine

from settings import get_settings


def _has_column(engine: Engine, table: str, column: str, schema: str = "public") -> bool:
    stmt = text(
        """
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = :schema
          AND table_name = :table
          AND column_name = :column
        LIMIT 1
        """
    )
    with engine.connect() as conn:
        res = conn.execute(stmt, {"schema": schema, "table": table, "column": column}).fetchone()
    return res is not None


def ensure_message_extensions(engine: Engine) -> None:
    """Ensure message_log has new production fields and create message_reads."""

    # Add columns to message_log (if missing).
    alter_stmts = []
    if not _has_column(engine, "message_log", "created_at"):
        alter_stmts.append("ALTER TABLE message_log ADD COLUMN created_at TIMESTAMP NULL")
    if not _has_column(engine, "message_log", "message_type"):
        alter_stmts.append("ALTER TABLE message_log ADD COLUMN message_type VARCHAR NOT NULL DEFAULT 'normal'")
    if not _has_column(engine, "message_log", "is_pinned"):
        alter_stmts.append("ALTER TABLE message_log ADD COLUMN is_pinned BOOLEAN NOT NULL DEFAULT FALSE")

    with engine.begin() as conn:
        for stmt in alter_stmts:
            conn.execute(text(stmt))

        # Create message_reads table (idempotent).
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS message_reads (
                    id SERIAL PRIMARY KEY,
                    message_id VARCHAR NOT NULL REFERENCES message_log(message_id) ON DELETE CASCADE,
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    is_read BOOLEAN NOT NULL DEFAULT FALSE,
                    read_at TIMESTAMP NULL,
                    is_archived BOOLEAN NOT NULL DEFAULT FALSE,
                    archived_at TIMESTAMP NULL,
                    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
                    CONSTRAINT uq_message_reads_message_user UNIQUE (message_id, user_id)
                )
                """
            )
        )

        # Indexes for performance.
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_message_reads_user_read ON message_reads(user_id, is_read)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_message_reads_user_archived ON message_reads(user_id, is_archived)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_message_log_created_at ON message_log(created_at)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_message_log_type ON message_log(message_type)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_message_log_pinned ON message_log(is_pinned)"))


def ensure_alerts_notifications(engine: Engine) -> None:
    """Create alerts/notifications tables + preferences (idempotent)."""

    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS alerts (
                    id SERIAL PRIMARY KEY,
                    alert_id VARCHAR NOT NULL UNIQUE,
                    title VARCHAR NOT NULL,
                    message TEXT NOT NULL,
                    alert_type VARCHAR NOT NULL DEFAULT 'operational_alert',
                    priority VARCHAR NOT NULL DEFAULT 'medium',
                    source VARCHAR NOT NULL DEFAULT 'system',
                    related_department VARCHAR NULL,
                    related_entity_type VARCHAR NULL,
                    related_entity_id VARCHAR NULL,
                    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
                    expires_at TIMESTAMP NULL,
                    is_active BOOLEAN NOT NULL DEFAULT TRUE,
                    is_acknowledged BOOLEAN NOT NULL DEFAULT FALSE,
                    acknowledged_by_user_id INTEGER NULL REFERENCES users(id),
                    acknowledged_at TIMESTAMP NULL,
                    resolved_by_user_id INTEGER NULL REFERENCES users(id),
                    resolved_at TIMESTAMP NULL,
                    generated_by_rule VARCHAR NULL,
                    recommendation_summary TEXT NULL
                )
                """
            )
        )

        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS notification_preferences (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
                    receive_in_app BOOLEAN NOT NULL DEFAULT TRUE,
                    receive_email BOOLEAN NOT NULL DEFAULT FALSE,
                    receive_sms BOOLEAN NOT NULL DEFAULT FALSE,
                    receive_push BOOLEAN NOT NULL DEFAULT FALSE,
                    critical_only BOOLEAN NOT NULL DEFAULT FALSE,
                    quiet_hours_start VARCHAR NULL,
                    quiet_hours_end VARCHAR NULL,
                    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
                )
                """
            )
        )

        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS notifications (
                    id SERIAL PRIMARY KEY,
                    notification_id VARCHAR NOT NULL UNIQUE,
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    alert_id INTEGER NULL REFERENCES alerts(id) ON DELETE SET NULL,
                    message_id VARCHAR NULL REFERENCES message_log(message_id) ON DELETE SET NULL,
                    channel VARCHAR NOT NULL DEFAULT 'in_app',
                    title VARCHAR NOT NULL,
                    body TEXT NOT NULL,
                    status VARCHAR NOT NULL DEFAULT 'delivered',
                    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
                    sent_at TIMESTAMP NULL,
                    delivered_at TIMESTAMP NULL,
                    read_at TIMESTAMP NULL,
                    failure_reason TEXT NULL,
                    retry_count INTEGER NOT NULL DEFAULT 0
                )
                """
            )
        )

        # Indexes
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_alerts_active ON alerts(is_active)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_alerts_type ON alerts(alert_type)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_alerts_priority ON alerts(priority)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_alerts_created_at ON alerts(created_at)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_alerts_dept ON alerts(related_department)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_notifications_user_status ON notifications(user_id, status)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_notifications_user_read ON notifications(user_id, read_at)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_notifications_created_at ON notifications(created_at)"))


def ensure_multi_tenant(engine: Engine) -> None:
    """Create tenants table + add tenant_id columns (idempotent).

    Strategy:
    - row-based multi-tenancy with tenant_id nullable initially (safe migration)
    - create a default tenant and backfill existing rows to that tenant

    NOTE: This is a lightweight migration helper. In production use Alembic.
    """

    settings = get_settings()
    default_slug = settings.default_tenant_slug

    with engine.begin() as conn:
        # Tenants table
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS tenants (
                    id SERIAL PRIMARY KEY,
                    name VARCHAR NOT NULL,
                    slug VARCHAR NOT NULL UNIQUE,
                    status VARCHAR NOT NULL DEFAULT 'active',
                    subscription_plan VARCHAR NOT NULL DEFAULT 'free',
                    timezone VARCHAR NULL,
                    country VARCHAR NULL,
                    default_language VARCHAR NULL DEFAULT 'en',
                    is_active BOOLEAN NOT NULL DEFAULT TRUE,
                    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
                )
                """
            )
        )

        # Make sure defaults exist even if the table was created by SQLAlchemy
        # without server defaults.
        conn.execute(text("ALTER TABLE tenants ALTER COLUMN status SET DEFAULT 'active'"))
        conn.execute(text("ALTER TABLE tenants ALTER COLUMN subscription_plan SET DEFAULT 'free'"))
        conn.execute(text("ALTER TABLE tenants ALTER COLUMN default_language SET DEFAULT 'en'"))
        conn.execute(text("ALTER TABLE tenants ALTER COLUMN is_active SET DEFAULT TRUE"))

        # Ensure default tenant exists (include required NOT NULL fields).
        conn.execute(
            text(
                """
                INSERT INTO tenants(name, slug, status, subscription_plan, default_language, is_active)
                VALUES (:name, :slug, 'active', 'free', 'en', TRUE)
                ON CONFLICT (slug) DO NOTHING
                """
            ),
            {"name": "Demo Hospital", "slug": default_slug},
        )

        # Backfill any NULLs in required columns (for existing rows in older DBs).
        conn.execute(text("UPDATE tenants SET status = 'active' WHERE status IS NULL"))
        conn.execute(text("UPDATE tenants SET subscription_plan = 'free' WHERE subscription_plan IS NULL"))
        conn.execute(text("UPDATE tenants SET default_language = 'en' WHERE default_language IS NULL"))
        conn.execute(text("UPDATE tenants SET is_active = TRUE WHERE is_active IS NULL"))

        # Fetch default tenant id.
        tenant_id = conn.execute(
            text("SELECT id FROM tenants WHERE slug = :slug LIMIT 1"),
            {"slug": default_slug},
        ).scalar_one()

        # Add tenant_id columns (nullable for now).
        # Core tables
        for table in [
            "users",
            "patients_flow",
            "appointments",
            "or_bookings",
            "staff_shifts",
            "message_log",
            "message_reads",
            "recommendation_records",
            "audit_events",
            "optimization_runs",
            "alerts",
            "notifications",
            "notification_preferences",
        ]:
            if not _has_column(engine, table, "tenant_id"):
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN tenant_id INTEGER NULL"))

        # Backfill existing records.
        for table in [
            "users",
            "patients_flow",
            "appointments",
            "or_bookings",
            "staff_shifts",
            "message_log",
            "message_reads",
            "recommendation_records",
            "audit_events",
            "optimization_runs",
            "alerts",
            "notifications",
            "notification_preferences",
        ]:
            conn.execute(text(f"UPDATE {table} SET tenant_id = :tid WHERE tenant_id IS NULL"), {"tid": int(tenant_id)})

        # Indexes (do NOT add FK constraints yet; keep migration safe across existing DBs)
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_users_tenant_id ON users(tenant_id)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_patients_flow_tenant_id ON patients_flow(tenant_id)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_message_log_tenant_id ON message_log(tenant_id)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_alerts_tenant_id ON alerts(tenant_id)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_notifications_tenant_id ON notifications(tenant_id)"))


def ensure_pipeline_runs(engine: Engine) -> None:
    """Create pipeline_runs table used by the scheduler (idempotent)."""

    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS pipeline_runs (
                    id SERIAL PRIMARY KEY,
                    tenant_id INTEGER NULL,
                    run_id VARCHAR NOT NULL UNIQUE,
                    status VARCHAR NOT NULL DEFAULT 'running',
                    step VARCHAR NULL,
                    started_at TIMESTAMP NOT NULL DEFAULT NOW(),
                    completed_at TIMESTAMP NULL,
                    details_json TEXT NULL
                )
                """
            )
        )
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_pipeline_runs_tenant_started ON pipeline_runs(tenant_id, started_at)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_pipeline_runs_tenant_status ON pipeline_runs(tenant_id, status)"))
