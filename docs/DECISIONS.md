# Decision Log (mirror of Notion Vora2.0 › Decision Log)

| Date | Decision | Why |
|---|---|---|
| 2026-10-23 | India only for now | Focus |
| 2026-10-23 | Self-hosted LiveKit, not Cloud; no Asterisk/Kamailio | No lock-in, SIP + warm transfer built in |
| 2026-10-23 | Sarvam for voice | Indian languages, official plugin |
| 2026-10-23 | Temporal for workflows | n8n embed licence ~$100k rejected |
| 2026-10-23 | Start fresh, Vora-OLD archived | Avoid confusion |
| 2026-10-23 | Stack: Next.js+TS web, Python FastAPI backend, Redis Streams events, ECS compute (LiveKit on EC2), Postgres analytics first, reseller layer deferred | One backend language, fewer systems |
| 2026-10-23 | Global later = separate AWS account, servers, product | Keep India build simple |
