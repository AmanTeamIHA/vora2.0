# LiveKit SIP resources (dev)

This directory is the inbound trunk for the dev softphone. It is not Terraform. It does not change security groups, the Elastic IP, or the SIP process config in `voice/livekit/`.

`infra.yml` still plans on a pull request that touches `infra/**`. That plan is the existing check. Do not apply it from a laptop.

## Inbound trunk

`inbound-trunk.json` is the trunk LiveKit SIP uses to accept a softphone INVITE (VORA2-46). The called number `+910000000000` is a stand-in, not a DID. Username, password, and signalling CIDRs are placeholders and are filled from the environment at apply time.

```bash
export LIVEKIT_URL=wss://livekit-dev.hellovora.ai
export LIVEKIT_API_KEY=...       # Secrets Manager vora2/dev/livekit
export LIVEKIT_API_SECRET=...    # same secret; do not paste it into git or chat
export VORA_SIP_AUTH_USERNAME=...
export VORA_SIP_AUTH_PASSWORD=...
export VORA_SIP_ALLOWED_CIDRS=203.0.113.10/32
infra/livekit/apply-inbound-trunk.sh
infra/livekit/apply-inbound-trunk.sh   # second run prints noop
lk sip inbound list
```

Store the softphone username and password in Secrets Manager. Do not write them into `inbound-trunk.json`.

Point the softphone at `livekit-dev.hellovora.ai:5060` UDP. LiveKit SIP does not accept REGISTER; it challenges the INVITE (401 or 407) and expects the same INVITE again with digest auth. Dial `+910000000000`. The source address has to fall inside `VORA_SIP_ALLOWED_CIDRS`.

`0.0.0.0/0` is rejected. Use the softphone's public signalling prefix.

Port 5060 stays closed until `sip_trunk_cidrs` is set (VORA2-30). This script does not open it. Codecs and DTMF are VORA2-48.

## Dispatch rule

`dispatch-rule.json` sends each accepted call to its own room and dispatches the voice worker (VORA2-47). The only called number in the map is `+910000000000`, the same placeholder the trunk accepts. Tenant "Vora Test" and agent "Demo receptionist" are the seed names. Their Postgres ids are not in git: `seed_demo` assigns them, and this directory does not query the database.

```bash
export LIVEKIT_URL=wss://livekit-dev.hellovora.ai
export LIVEKIT_API_KEY=...       # Secrets Manager vora2/dev/livekit
export LIVEKIT_API_SECRET=...    # same secret; do not paste it into git or chat
export VORA_TEST_TENANT_ID=...   # tenants.id where name = 'Vora Test'
export VORA_TEST_AGENT_ID=...    # agents.id where name = 'Demo receptionist'
infra/livekit/apply-inbound-trunk.sh
infra/livekit/apply-dispatch-rule.sh
infra/livekit/apply-dispatch-rule.sh   # second run prints noop
lk sip dispatch list
```

The rule is bound to trunk `vora2-dev-softphone`. Apply the trunk first. Room metadata on the rule is `{"agent_id","tenant_id"}` with those ids. The agent entry is the empty name the voice worker registers with.

livekit-server v1.13.10 names the room `call-_<caller>_<random>`, not `call-{uuid}`. The random part changes on every call. A called number that is not in the map matches nothing: LiveKit returns 404 and leaves no room. `departure_timeout` is 10 seconds, so after the caller and the agent have both left, the room closes on that timer.

This script does not open port 5060. Until VORA2-30 sets `sip_trunk_cidrs`, a softphone on the public internet cannot reach the trunk, so the call check below cannot be run from here.

```bash
# After 5060 is open to the softphone and the dispatch rule is applied:
# dial +910000000000, then:
lk room list
# a room named call-_<caller>_<random>
# metadata {"tenant_id":"<VORA_TEST_TENANT_ID>","agent_id":"<VORA_TEST_AGENT_ID>"}
lk room participants list 'call-_<caller>_<random>'
# the agent participant is in the room
# hang up, wait 10 seconds, then:
lk room list
# that room is gone
```
