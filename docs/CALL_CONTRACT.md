# Call contract

Shared lifecycle for Lanes A–D. This file is the contract. Publishing events, persisting them from a worker, and writing recordings are later tickets (VORA2-21, VORA2-16). No transcript event lives here.

## Lifecycle

```
call.created → call.ringing → call.answered → turn.completed → call.ended
```

`turn.completed` repeats once per spoken turn. The other events happen once per call.

Every event carries:

| Field | Type | Meaning |
|---|---|---|
| `event` | string | One of the names above |
| `tenant_id` | uuid | Tenant that owns the call |
| `call_id` | uuid | Call row id |
| `occurred_at` | timestamptz | When the fact happened (offset required) |

Extra fields:

| Event | Fields |
|---|---|
| `call.created` | `agent_id`, `agent_version_id` |
| `call.ringing` | — |
| `call.answered` | — |
| `turn.completed` | `turn_index` (≥ 0), `stt_ms`, `llm_ms`, `tts_ms`, `ttfw_ms` (each ≥ 0) |
| `call.ended` | `reason` (non-empty), `duration_ms` (≥ 0), `recording_key` (string or null) |

`duration_ms` is the call duration, in milliseconds. `recording_key` is the S3 object key. It is null when the call ends before a recording exists. `ttfw_ms` is time to first word for that turn.

The worker's current metric names map onto the turn event:

| Worker metric | Contract field |
|---|---|
| `eos_to_stt_final` | `stt_ms` |
| `llm_first_token` | `llm_ms` |
| `tts_first_byte` | `tts_ms` |
| `time_to_first_word` | `ttfw_ms` |

Models live in `packages/contracts`. Both the API and the voice worker import them the same way:

```python
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
```

`parse_lifecycle_event` accepts a dict or a JSON string and returns the matching model. Unknown event names are rejected.

## Redis Streams

| Key | Constant | Who reads it |
|---|---|---|
| `calls:events` | `CALLS_EVENTS_STREAM` | Global live view |
| `calls:events:{tenant_id}` | `tenant_calls_stream(tenant_id)` | That tenant only |

`{tenant_id}` is the canonical UUID string. Publishers append the same JSON body to both keys. This ticket does not publish or consume.

## Tables

Migration `0010_call_lifecycle` (revises `0009_integrations`). Every table has `tenant_id` and forced row-level security: `tenant_id::text = current_setting('app.tenant_id', true)`. `vora_app` does not bypass RLS. `vora_admin` does.

`calls` already exists. The migration adds:

| Column | Type | Notes |
|---|---|---|
| `status` | text | `created`, `ringing`, `answered`, `ended`. Default `created` |
| `ringing_at` | timestamptz | null until `call.ringing` |
| `answered_at` | timestamptz | null until `call.answered` |
| `ended_at` | timestamptz | null until `call.ended` |
| `end_reason` | text | `call.ended.reason` |
| `duration_ms` | int | `call.ended.duration_ms`, null until the call ends |

Existing columns stay: `id`, `tenant_id`, `agent_id`, `agent_version_id`, `created_at`. A new call row can still be inserted with only those, which is what `POST /internal/calls/start` does today.

`call_turns`: `id`, `tenant_id`, `call_id`, `turn_index`, `stt_ms`, `llm_ms`, `tts_ms`, `ttfw_ms`, `created_at`. Unique `(call_id, turn_index)`.

`call_recordings`: `id`, `tenant_id`, `call_id`, `recording_key`, `created_at`. `recording_key` is unique. A row exists only when a key exists.

Child rows reference `calls.id` with `ON DELETE CASCADE`.

## Out of scope

- Publishing or consuming the streams (VORA2-21)
- LiveKit egress and the S3 write (VORA2-16)
- API routes and UI
- Transcript text (separate contract ticket if VORA2-23c needs it)
