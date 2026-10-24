# voice/sip

Inbound trunk for the dev softphone. The desired trunk is `infra/livekit/inbound-trunk.json`. `apply.py` fills the placeholders from the environment and creates or replaces that trunk through `lk`. A second run that already matches does not call create or update.

```bash
pytest voice/sip -q
```

Out of scope: dispatch rules (VORA2-47), codecs and DTMF (VORA2-48), carrier credentials, the test DID, and security group changes (VORA2-30).
