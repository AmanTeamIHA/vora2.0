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

Port 5060 stays closed until `sip_trunk_cidrs` is set (VORA2-30). This script does not open it. After the trunk matches, LiveKit still answers 404 until a dispatch rule exists (VORA2-47). Codecs and DTMF are VORA2-48.
