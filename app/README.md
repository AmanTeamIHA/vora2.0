# app/ — Platform App

- Core API: Python FastAPI (auth, tenants, agents, leads, campaigns, webhooks)
- Web: Next.js + TypeScript — Super Admin console + tenant dashboard, one codebase, role-based
- Postgres: tenant_id + Row-Level Security on every table
- Live call view: Redis Streams → WebSocket
- Super Admin impersonation always written to audit_log; kill switches per tenant/campaign

Linear project: Platform App.
