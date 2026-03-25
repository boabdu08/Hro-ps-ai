from pydantic import BaseModel, model_validator


class TenantLoginMixin(BaseModel):
    # Canonical field is `tenant` (slug). We also accept legacy `tenant_slug`.
    tenant: str | None = None
    # Backwards compatible: clients can omit this and default tenant will be used.
    tenant_slug: str | None = None


class LoginRequest(TenantLoginMixin):
    # Canonical login identifier is `username`. We also accept `email` for compatibility.
    username: str | None = None
    email: str | None = None
    password: str

    @model_validator(mode="before")
    @classmethod
    def _normalize_compat(cls, values):
        # Support clients sending {tenant: "..."} instead of {tenant_slug: "..."}
        if isinstance(values, dict):
            tenant = values.get("tenant")
            if tenant and not values.get("tenant_slug"):
                values["tenant_slug"] = tenant

            # Support clients sending {email: "..."} instead of {username: "..."}
            email = values.get("email")
            if email and not values.get("username"):
                values["username"] = email
        return values


class UserResponse(BaseModel):
    username: str
    name: str | None = None
    role: str | None = None
    department: str | None = None