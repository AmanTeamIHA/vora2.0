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
| 2026-10-24 | Vora 2.0 shares AWS account 585008088038 with CallAtlas v2, isolated by its own network and IAM boundaries (own VPC 10.20.0.0/16, project=vora2 tags, a scoped vora2 deploy role with a permission boundary, and its own Terraform state). Dev URL playground-dev.hellovora.ai behind Cloudflare Access | One account. The NOC already runs it. Cost is split by tags |
| 2026-10-24 | UI direction: Apple-style look and feel on top of the Atlas-style structure, layout and positioning already built, including the Atlas advertiser view adapted into the tenant view. Supersedes the earlier "follow ATLAS admin" vs "Apple-style" conflict | Decided 24 Oct 2026. QA and DevOps build and test against this direction |
