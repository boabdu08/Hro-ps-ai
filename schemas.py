from pydantic import BaseModel


class TenantLoginMixin(BaseModel):
    # Backwards compatible: clients can omit this and default tenant will be used.
    tenant_slug: str | None = None


class LoginRequest(TenantLoginMixin):
    username: str
    password: str


class UserResponse(BaseModel):
    username: str
    name: str | None = None
    role: str | None = None
    department: str | None = None