def test_api_suite_imports_call_contract() -> None:
    from contracts import (
        CALLS_EVENTS_STREAM,
        CallAnswered,
        CallCreated,
        CallEnded,
        CallRinging,
        TurnCompleted,
        parse_lifecycle_event,
        tenant_calls_stream,
    )

    assert CALLS_EVENTS_STREAM == "calls:events"
    assert CallCreated.__name__ == "CallCreated"
    assert CallRinging.__name__ == "CallRinging"
    assert CallAnswered.__name__ == "CallAnswered"
    assert TurnCompleted.__name__ == "TurnCompleted"
    assert CallEnded.__name__ == "CallEnded"
    assert callable(parse_lifecycle_event)
    assert callable(tenant_calls_stream)
