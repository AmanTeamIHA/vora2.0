# app/ — Platform App

- Core API: Python FastAPI (auth, tenants, agents, leads, campaigns, webhooks)
- Web: Next.js + TypeScript — Super Admin console + tenant dashboard, one codebase, role-based
- Postgres: tenant_id + Row-Level Security on every table
- Live call view: Redis Streams → WebSocket
- Super Admin impersonation always written to audit_log; kill switches per tenant/campaign

Linear project: Platform App.

## Local

```bash
docker compose up --build
```

- Web: http://localhost:3000 (`/admin`, `/t/{slug}`)
- API: http://localhost:8000/healthz

Postgres 16 and Redis 7 come up with the compose file. Credentials in that file are local only.

`GET /users` returns only the rows for the `X-Tenant-Id` header. The API connects as `vora_app` (RLS on). Super Admin reads go through `vora_admin` and write `audit_log`.

Super Admin sign-in is `/admin/login` (password, then authenticator code). Create the first owner with `OWNER_EMAIL` and `OWNER_PASSWORD` set, then:

```bash
cd app/api && uv run python -m vora_api.bootstrap_owner
```

The command prints a one-time `otpauth://` URI. Add it to an authenticator app. Do not commit the password.
