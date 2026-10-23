from contextvars import ContextVar

current_impersonation: ContextVar[dict[str, str] | None] = ContextVar(
    "current_impersonation",
    default=None,
)
