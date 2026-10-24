# Vora 2.0 — Architecture (Draft v1, 23 Oct 2026)

Mirror of Notion Vora2.0 › Architecture. Notion is the source of truth.

**Scope: India only.** One AWS account, region ap-south-1 (Mumbai). All data, calls, recordings and logs stay in India. A global version later = separate AWS account, servers and product. Nothing here is built to be multi-region.

Items marked **(approved 23 Oct)** were approved by Nick on 23 Oct 2026.

---

## 1. Hierarchy and roles (top down)

**Level 0: Super Admin (IHA internal)**
- Roles: Owner (Nick), Platform Admin, Support, Finance, Read-only.
- Can do: create/suspend tenants, set plans and limits, assign phone numbers and caller-ID pools, set per-tenant concurrency, change rates, top up or adjust wallets, impersonate a tenant (with audit), see global live calls, trunk usage, Sarvam spend, margins, system health.
- Global settings: trunk config, Sarvam keys, default voices and languages, prompt templates, feature flags per tenant, kill switch per tenant or campaign.

**Level 1: Tenant (customer company)**
- Roles: Tenant Admin, Manager, Agent Builder, Human Agent (receives transfers), Viewer.
- Owns: agents, numbers, integrations, workflows, campaigns, leads, wallet, users.

**Level 2: Tenant users**: see only their tenant. Human Agents get a simple view: incoming transfers, lead summary, callbacks.

Reseller/partner layer: not in v1, but the data model leaves room for a `parent_tenant_id`. **(approved 23 Oct)**

---

## 2. System components

1. **Web App**: Super Admin console + Tenant dashboard, one codebase, role-based. Next.js + TypeScript. **(approved 23 Oct)**
2. **Core API**: auth, tenants, agents, leads, campaigns, billing, webhooks. Python FastAPI. **(approved 23 Oct)** Same language as the voice agents and Temporal workers, so it's one backend language.
3. **Voice layer**: self-hosted LiveKit Server + LiveKit SIP on EC2, connected to our SIP trunk (1,000 channels). Handles inbound, outbound, transfers and recording (LiveKit Egress to S3).
4. **Agent Workers**: LiveKit Agents (Python) + Sarvam STT/TTS/LLM. Autoscaled EC2 group. Each call loads its agent config + caller memory at start.
5. **Workflow Engine**: self-hosted Temporal + Python workers. Runs campaigns, dialer pacing, retries, post-call actions, integrations.
6. **Dialer Scheduler**: a Temporal workflow that hands out channel slots globally, using per-tenant caps and a fair share. Outbound is capped at ~70% of trunk capacity.
7. **Integration Hub**: connectors (Meta Lead Ads, Google Sheets, Google/M365 Calendar, WhatsApp BSP, Email, CRMs) + MCP client for agent tools. Credentials are encrypted per tenant.
8. **Event bus**: Redis Streams for live events (call started, connected, ended), pushed to the dashboard over WebSocket. **(approved 23 Oct)**
9. **Billing service**: metering (minutes, transfer legs, WhatsApp, setup fees), prepaid wallet, Razorpay. A wallet check happens before every call is dialled.

---

## 3. Data layer

- **PostgreSQL (RDS, Multi-AZ)**: main database. Every table carries `tenant_id`, enforced with Row-Level Security.
- **Redis (ElastiCache)**: live call state, concurrency counters, rate limits, caching.
- **S3 (Mumbai)**: recordings, transcripts, uploaded lead files. Encrypted, with per-tenant prefixes and retention policies.
- **Temporal DB**: its own Postgres, separate from the app database.
- Analytics: Postgres to start. Move to ClickHouse later if call volume demands it. **(approved 23 Oct)**

**Core tables**: tenants, users, roles, plans, phone_numbers, caller_id_pools, agents, agent_versions, knowledge_bases, integrations, workflows, workflow_runs, campaigns, contacts, call_attempts, calls, transcripts, dispositions, transfers, lead_memory, wallet_ledger, usage_events, invoices, audit_log.

Rule: agent configs are versioned. A call always records which `agent_version` handled it.

---

## 4. Key flows

**Inbound call**: trunk → LiveKit SIP → number lookup gives tenant + agent → agent worker joins → pre-call memory load → conversation with tools → post-call summary, disposition, CRM sync, workflow trigger.

**Outbound campaign**: upload/Sheet/Meta lead → contacts → campaign workflow → scheduler grants slot → wallet check → LiveKit dials from caller-ID pool → answer detection → AI talks → disposition → retry rules or next steps.

**Warm transfer**: transfer tool → dial 3CX extension (SIP) or mobile (PSTN) → private AI brief + WhatsApp summary → bridge → AI leaves. No answer in ~20s → back to caller, book callback.

**Billing**: every call/transfer/message → usage_event → wallet_ledger debit. Low balance → alert. Zero balance → campaigns pause.

---

## 5. Infrastructure (AWS Mumbai, single account)

- VPC with private subnets. Only LiveKit SIP/RTP and the web/API load balancer are public.
- Environments: dev and prod (staging later). Separate VPCs.
- Compute: EC2 for LiveKit (needs host networking for RTP). ECS or EC2 autoscaling for API, agent workers, Temporal workers. **(approved 23 Oct)**
- CI/CD: GitHub Actions → build → deploy to dev → manual promote to prod.
- Observability: CloudWatch + Grafana. Per-call latency metrics (time to first word, STT/LLM/TTS time).
- Secrets: infrastructure secrets (database, JWT, internal auth, the integration encryption key) stay in AWS Secrets Manager / SSM. Integration API keys such as Sarvam are entered in Global Settings and stored encrypted in Postgres.

---

## 6. Security and guardrails

- Tenant isolation at the database level (RLS) + API checks.
- Super Admin impersonation is logged in audit_log.
- Money-moving tools: caller verification, amount limits, audit log. The AI never moves money on its own.
- Per-tenant and global kill switches for campaigns.

---

## 7. Repo layout (mirrors the six domains)

```
vora2.0/
  infra/        Foundation & Infra (Terraform, CI)
  voice/        Telephony & Voice (LiveKit config, agent workers)
  brain/        Agent Brain & Integrations (tools, MCP, memory)
  workflows/    Workflow Engine (Temporal workers, dialer)
  app/          Platform App (Next.js web + FastAPI)
  billing/      Billing (metering, wallet, Razorpay)
  docs/         architecture, decisions (mirrors Notion)
```

---

## 8. Build order

1. Infra + LiveKit + trunk + one Sarvam agent answering a call (prove latency).
2. Outbound single call + answer detection + fast first word.
3. Core API + Postgres + tenants + Super Admin console.
4. Agent editor + tenant dashboard + live call view.
5. Campaigns + dialer scheduler + retries.
6. Warm transfer.
7. Workflows: Meta/Sheets triggers, calendar, WhatsApp, email.
8. Billing + wallet + Razorpay.
9. Migrate the 35 live agents.

## Open

- Sarvam concurrency limit (sets the real call ceiling).
