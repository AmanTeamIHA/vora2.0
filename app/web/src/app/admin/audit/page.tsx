"use client";

import { useEffect, useState } from "react";

type Entry = {
  id: string;
  action: string;
  actor_email: string | null;
  tenant_name: string | null;
  detail: string | null;
  created_at: string;
};

type Tenant = { id: string; name: string };

export default function AuditPage() {
  const [entries, setEntries] = useState<Entry[]>([]);
  const [tenants, setTenants] = useState<Tenant[]>([]);
  const [actor, setActor] = useState("");
  const [action, setAction] = useState("");
  const [tenantId, setTenantId] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");

  const params = new URLSearchParams();
  if (actor) params.set("actor", actor);
  if (action) params.set("action", action);
  if (tenantId) params.set("tenant_id", tenantId);
  if (dateFrom) params.set("date_from", dateFrom);
  if (dateTo) params.set("date_to", dateTo);
  const query = params.toString();

  useEffect(() => {
    let cancelled = false;
    async function run() {
      const [auditBody, tenantBody] = await Promise.all([
        fetch(`/api/admin/audit?${query}`, { credentials: "include" }).then((response) =>
          response.json(),
        ),
        fetch("/api/admin/tenants", { credentials: "include" }).then((response) => response.json()),
      ]);
      if (cancelled) return;
      setEntries((auditBody as { entries?: Entry[] }).entries ?? []);
      setTenants((tenantBody as { tenants?: Tenant[] }).tenants ?? []);
    }
    void run();
    return () => {
      cancelled = true;
    };
  }, [query]);

  return (
    <div className="flex flex-col gap-6">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-[32px] leading-none font-semibold tracking-[-0.8px]">Audit log</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Every platform write. Rows cannot be edited or deleted.
          </p>
        </div>
        <a className="text-sm text-primary underline" href={`/api/admin/audit.csv?${query}`}>
          Export CSV
        </a>
      </header>
      <form className="flex flex-wrap gap-2" onSubmit={(event) => event.preventDefault()}>
        <input
          className="h-10 rounded-lg border border-border bg-card px-3 text-sm"
          placeholder="Actor email"
          aria-label="Actor"
          value={actor}
          onChange={(event) => setActor(event.target.value)}
        />
        <input
          className="h-10 rounded-lg border border-border bg-card px-3 text-sm"
          placeholder="Action"
          aria-label="Action"
          value={action}
          onChange={(event) => setAction(event.target.value)}
        />
        <select
          className="h-10 rounded-lg border border-border bg-card px-3 text-sm"
          aria-label="Tenant"
          value={tenantId}
          onChange={(event) => setTenantId(event.target.value)}
        >
          <option value="">Any tenant</option>
          {tenants.map((tenant) => (
            <option key={tenant.id} value={tenant.id}>
              {tenant.name}
            </option>
          ))}
        </select>
        <input
          className="h-10 rounded-lg border border-border bg-card px-3 text-sm"
          type="date"
          aria-label="From"
          value={dateFrom}
          onChange={(event) => setDateFrom(event.target.value)}
        />
        <input
          className="h-10 rounded-lg border border-border bg-card px-3 text-sm"
          type="date"
          aria-label="To"
          value={dateTo}
          onChange={(event) => setDateTo(event.target.value)}
        />
      </form>
      <div className="overflow-x-auto rounded-2xl bg-white shadow-[0_0_0_1px_rgba(0,0,0,0.04)]">
        <table className="w-full min-w-[720px] text-left text-sm">
          <thead className="text-xs font-normal text-[#86868B]">
            <tr>
              <th className="px-3 py-2 font-medium">When</th>
              <th className="px-3 py-2 font-medium">Action</th>
              <th className="px-3 py-2 font-medium">Actor</th>
              <th className="px-3 py-2 font-medium">Tenant</th>
              <th className="px-3 py-2 font-medium">Detail</th>
            </tr>
          </thead>
          <tbody>
            {entries.map((entry) => (
              <tr key={entry.id} className="border-t border-border">
                <td className="px-3 py-2 font-mono text-xs">{entry.created_at}</td>
                <td className="px-3 py-2">{entry.action}</td>
                <td className="px-3 py-2">{entry.actor_email}</td>
                <td className="px-3 py-2">{entry.tenant_name}</td>
                <td className="px-3 py-2">{entry.detail}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
