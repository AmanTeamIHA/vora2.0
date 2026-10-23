from contextvars import ContextVar

current_tenant_id: ContextVar[str] = ContextVar("current_tenant_id", default="")
