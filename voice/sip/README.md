# voice/sip

Inbound trunk and dispatch rule for the dev softphone.

`infra/livekit/inbound-trunk.json` is the trunk (VORA2-46). `apply.py` fills its placeholders from the environment and creates or replaces that trunk through `lk`. A second run that already matches does not call create or update.

`infra/livekit/dispatch-rule.json` is the called-number map (VORA2-47). The seed route is `+910000000000` → tenant "Vora Test" / agent "Demo receptionist". `apply_dispatch.py` fills the tenant and agent ids from the environment, binds the rule to the `vora2-dev-softphone` trunk, and creates or replaces that rule. A second run that already matches does not call create or update.

The rule is an individual dispatch rule with room prefix `call-`. livekit-server v1.13.10 names the room `call-_<caller>_<random>`. The random suffix is new on every call, so the room is never reused. That server has no `call-{uuid}` template. Room metadata is `{"tenant_id","agent_id"}`. The agent job uses the worker's registered name, which is empty: `voice/agent` calls `WorkerOptions` with no `agent_name`, and the dev task does not set `LIVEKIT_AGENT_NAME`.

A called number that is not in the map matches no rule. LiveKit answers 404 and does not create a room. `lookup_number` logs `rejected unknown called number …; no room created`.

```bash
pytest voice/sip -q
```

Out of scope: DB-backed number lookup (VORA2-17), the real DID and opening port 5060 (VORA2-30), codecs and DTMF (VORA2-48), call records (Lane C).
