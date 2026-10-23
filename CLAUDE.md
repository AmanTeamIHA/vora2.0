# Vora 2.0: Project Instructions

## What this is
Vora 2.0 is an AI employee platform for Indian businesses. AI agents call leads (inbound and outbound), qualify, book meetings, send WhatsApp/email, warm-transfer to humans, and sync to CRMs. Everything runs in one multi-tenant platform with a Super Admin layer.

## Hard scope
- India only. One AWS account, ap-south-1 (Mumbai). All data, calls, recordings and logs stay in India.
- Global is out of scope: a separate account, servers and product later. Never add multi-region code.
- Fresh build. Nothing from Vora-OLD (old repo, Notion, Linear) applies. Do not copy old code.

## Locked stack (do not change without a Decision Log entry)
- Telephony: self-hosted LiveKit Server + LiveKit SIP on EC2, own SIP trunk (1,000 channels). No LiveKit Cloud, no Asterisk, no Kamailio, no Twilio/Plivo.
- Voice: Sarvam STT/TTS/LLM via livekit-plugins-sarvam.
- Agents: LiveKit Agents (Python).
- Workflows: Temporal (self-hosted, MIT) + React Flow canvas. No n8n, Activepieces, Windmill.
- Backend: Python FastAPI. Frontend: Next.js + TypeScript (Super Admin + tenant in one app, role-based).
- Data: PostgreSQL (RDS) with tenant_id + Row-Level Security on every table; Redis (ElastiCache) for live state, counters, Redis Streams events; S3 Mumbai for recordings/files.
- Compute: ECS for API and workers; LiveKit on plain EC2.
- Billing: prepaid wallet + Razorpay.

## Repo layout (mirrors the six domains)
infra/ voice/ brain/ workflows/ app/ billing/ docs/
Each domain = one Linear project = one Notion domain page.

## Sources of truth
- Linear team Vora 2.0: tickets, bugs, build status.
- Notion Vora2.0: Architecture, Decision Log, domain pages, Daily Handoff.
- Repo docs/: mirrors Notion architecture and decisions.
- Obsidian Vora2.0 folder: local mirror.

## Working rules
1. Before starting: read Notion Home, Architecture and the latest Daily Handoff.
2. Every change maps to a Linear ticket. Branch name = ticket ID.
3. Never commit straight to main. Use a PR and deploy to dev first, then manually promote to prod.
4. Any architecture change gets a Decision Log entry first.
5. Bugs go in Linear with the Bug label, never as silent fixes.
6. End every session with a Daily Handoff entry: done, in progress, blockers, next.
7. No secrets in code. Use AWS Secrets Manager/SSM.
8. Every tenant query is scoped by tenant_id. Never bypass RLS.
9. Agent configs are versioned, and every call stores its agent_version.
10. Money-moving tools need caller verification, amount limits and an audit log. The AI never moves money on its own.
11. Super Admin impersonation is always logged.
12. Measure voice latency (time to first word, STT/LLM/TTS) on every voice change.

## Build order
1. Infra + LiveKit + trunk + one Sarvam agent answering a call.
2. Outbound call + answer detection + fast first word.
3. Core API + tenants + Super Admin console.
4. Agent editor + tenant dashboard + live call view.
5. Campaigns + dialer scheduler + retries.
6. Warm transfer (3CX SIP + mobile PSTN).
7. Workflows: Meta/Sheets triggers, calendar, WhatsApp, email.
8. Billing + wallet + Razorpay.
9. Migrate the 35 live agents.

## Communication
No preamble. Be direct, push back when something is wrong, say no when warranted. Keep it short.
