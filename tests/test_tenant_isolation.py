"""Multi-tenant isolation regression tests.

Proves that tenant A cannot read tenant B's rows through the tenant-scoped
query paths used by the API (users-for-scope resolution, alert fan-out, and
direct tenant-filtered queries on operational tables).

Runs against an isolated in-memory SQLite database — no live Postgres needed.
"""

import os

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("APP_ENV", "test")

from database import Base  # noqa: E402
from models import Alert, Notification, PatientFlow, Tenant, User  # noqa: E402


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    TestSession = sessionmaker(bind=engine, expire_on_commit=False)
    session = TestSession()

    # Two tenants, one admin each, plus operational rows per tenant.
    t_a = Tenant(name="Hospital A", slug="hospital-a")
    t_b = Tenant(name="Hospital B", slug="hospital-b")
    session.add_all([t_a, t_b])
    session.commit()

    session.add_all(
        [
            User(tenant_id=t_a.id, username="admin_a", name="Admin A", role="admin", department="Management", password="x"),
            User(tenant_id=t_a.id, username="nurse_a", name="Nurse A", role="nurse", department="ER", password="x"),
            User(tenant_id=t_b.id, username="admin_b", name="Admin B", role="admin", department="Management", password="x"),
            PatientFlow(tenant_id=t_a.id, datetime="2026-01-01 00:00:00", patients=100.0),
            PatientFlow(tenant_id=t_a.id, datetime="2026-01-01 01:00:00", patients=110.0),
            PatientFlow(tenant_id=t_b.id, datetime="2026-01-01 00:00:00", patients=55.0),
        ]
    )
    session.commit()

    yield session, int(t_a.id), int(t_b.id)
    session.close()
    engine.dispose()


class TestUserScopeIsolation:
    def test_users_for_scope_only_returns_own_tenant(self, db):
        from api import _users_for_scope

        session, tid_a, tid_b = db
        users_a = _users_for_scope(session, tid_a, "all", "All Departments")
        users_b = _users_for_scope(session, tid_b, "all", "All Departments")

        assert {u.username for u in users_a} == {"admin_a", "nurse_a"}
        assert {u.username for u in users_b} == {"admin_b"}

    def test_role_filter_does_not_leak_across_tenants(self, db):
        from api import _users_for_scope

        session, tid_a, tid_b = db
        admins_b = _users_for_scope(session, tid_b, "admin", None)
        assert all(u.tenant_id == tid_b for u in admins_b)
        assert "admin_a" not in {u.username for u in admins_b}


class TestAlertNotificationIsolation:
    def test_alert_notifications_stay_within_tenant(self, db):
        from api import create_alert_and_notify

        session, tid_a, tid_b = db
        create_alert_and_notify(
            db=session,
            tenant_id=tid_a,
            title="Capacity warning A",
            message="Tenant A only",
            alert_type="capacity_alert",
            priority="high",
            source="test",
        )

        alerts_b = session.query(Alert).filter(Alert.tenant_id == tid_b).all()
        assert alerts_b == []

        notif_user_ids = {n.user_id for n in session.query(Notification).all()}
        b_user_ids = {u.id for u in session.query(User).filter(User.tenant_id == tid_b)}
        assert notif_user_ids.isdisjoint(b_user_ids)

    def test_alert_created_for_own_tenant(self, db):
        from api import create_alert_and_notify

        session, tid_a, _ = db
        alert = create_alert_and_notify(
            db=session,
            tenant_id=tid_a,
            title="Surge",
            message="ER surge",
            alert_type="forecast_alert",
            priority="high",
            source="test",
        )
        assert int(alert.tenant_id) == tid_a


class TestOperationalDataIsolation:
    def test_patient_flow_rows_are_tenant_scoped(self, db):
        session, tid_a, tid_b = db
        rows_a = session.query(PatientFlow).filter(PatientFlow.tenant_id == tid_a).all()
        rows_b = session.query(PatientFlow).filter(PatientFlow.tenant_id == tid_b).all()
        assert len(rows_a) == 2
        assert len(rows_b) == 1
        assert all(float(r.patients) >= 100.0 for r in rows_a)
        assert all(float(r.patients) < 100.0 for r in rows_b)

    def test_all_tenant_scoped_models_carry_tenant_id(self):
        """Every operational table must have a tenant_id column (schema regression guard)."""
        import models as m

        tenant_scoped = [
            m.PatientFlow, m.Appointment, m.ORBooking, m.StaffShift,
            m.Alert, m.Notification, m.MessageLog, m.User,
        ]
        for model in tenant_scoped:
            assert hasattr(model, "tenant_id"), f"{model.__name__} is missing tenant_id"
