"""Idempotent demo seed for PostgreSQL.

Creates:
- tenant: demo-hospital (or DEFAULT_TENANT_SLUG)
- users: admin1/doctor1/nurse1 with password 123456

Safe to run repeatedly.
"""

from __future__ import annotations

from database import SessionLocal, init_db
from settings import get_settings
from auth import hash_password, verify_password
from models import Tenant, User


def seed_demo() -> None:
    settings = get_settings()
    init_db()

    db = SessionLocal()
    try:
        slug = (settings.default_tenant_slug or "demo-hospital").strip() or "demo-hospital"
        tenant = db.query(Tenant).filter(Tenant.slug == slug).first()
        if tenant is None:
            tenant = Tenant(name="Demo Hospital", slug=slug)
            db.add(tenant)
            db.commit()
            db.refresh(tenant)

        pwd = "123456"
        hashed = hash_password(pwd)
        desired = [
            {"username": "admin1", "name": "Hospital Admin", "role": "admin", "department": "Management"},
            {"username": "doctor1", "name": "Dr. Ahmed", "role": "doctor", "department": "ER"},
            {"username": "nurse1", "name": "Nurse Mona", "role": "nurse", "department": "General Ward"},
        ]

        for u in desired:
            row = (
                db.query(User)
                .filter(User.tenant_id == int(tenant.id), User.username == u["username"])
                .first()
            )
            if row is None:
                db.add(
                    User(
                        tenant_id=int(tenant.id),
                        username=u["username"],
                        name=u["name"],
                        role=u["role"],
                        department=u["department"],
                        password=hashed,
                    )
                )
            else:
                # Upgrade bad/old passwords.
                if (not row.password) or ("$" not in str(row.password)) or (not verify_password(pwd, str(row.password))):
                    row.password = hashed
                row.name = row.name or u["name"]
                row.role = row.role or u["role"]
                row.department = row.department or u["department"]

        db.commit()
        print(f"Seeded demo tenant={slug} users=admin1/doctor1/nurse1 (pwd=123456)")
    finally:
        db.close()


if __name__ == "__main__":
    seed_demo()
