from uuid import UUID

from contracts import CALLS_EVENTS_STREAM, tenant_calls_stream


def test_global_and_per_tenant_stream_names() -> None:
    tenant_id = UUID("11111111-1111-1111-1111-111111111111")
    assert CALLS_EVENTS_STREAM == "calls:events"
    assert tenant_calls_stream(tenant_id) == f"calls:events:{tenant_id}"
    assert tenant_calls_stream(tenant_id) != CALLS_EVENTS_STREAM
