from vora_api.models import Plan, TenantLimit


def effective_limits(plan: Plan, override: TenantLimit | None) -> dict[str, object]:
    """Plan values, replaced only where this tenant has an override."""

    def pick(override_value: int | None, plan_value: int) -> int:
        return plan_value if override_value is None else override_value

    override = override or TenantLimit(tenant_id=plan.id)
    return {
        "plan": plan.name,
        "per_minute_rate_paise": pick(override.per_minute_rate_paise, plan.per_minute_rate_paise),
        "transfer_leg_rate_paise": pick(
            override.transfer_leg_rate_paise, plan.transfer_leg_rate_paise
        ),
        "max_concurrent_calls": pick(override.max_concurrent_calls, plan.max_concurrent_calls),
        "max_outbound_share_percent": plan.max_outbound_share_percent,
        "max_agents": plan.max_agents,
        "languages": list(plan.languages or []),
        "feature_flags": dict(plan.feature_flags or {}),
    }
