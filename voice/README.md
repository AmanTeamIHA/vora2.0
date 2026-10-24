# voice/ — Telephony & Voice

- Self-hosted LiveKit Server + LiveKit SIP config (EC2, host networking for RTP). Dev files: `voice/livekit/`.
- Own SIP trunk, 1,000 channels; caller-ID pools
- LiveKit Agents (Python) workers with livekit-plugins-sarvam (STT/TTS/LLM)
- Egress recordings → S3; answer detection; pre-generated first line
- Warm transfer: 3CX extension (SIP) or mobile (PSTN), ~20s no-answer fallback

Rule: measure time to first word + STT/LLM/TTS latency on every change.
Linear project: Telephony & Voice.
