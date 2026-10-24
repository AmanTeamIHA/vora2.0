"use client";

import { useEffect, useState, type FormEvent } from "react";
import { Button } from "@/components/ui/button";

type NumberRow = {
  id: string;
  e164: string;
  status: string;
  tenant_id: string | null;
  tenant_name: string | null;
  pool_name: string | null;
  inbound_agent_id: string | null;
};

type Tenant = { id: string; name: string };
type Pool = { id: string; tenant_id: string; name: string };

export default function NumbersPage() {
  const [numbers, setNumbers] = useState<NumberRow[]>([]);
  const [tenants, setTenants] = useState<Tenant[]>([]);
  const [pools, setPools] = useState<Pool[]>([]);
  const [paste, setPaste] = useState("");
  const [assignId, setAssignId] = useState("");
  const [tenantId, setTenantId] = useState("");
  const [agentId, setAgentId] = useState("");
  const [poolTenant, setPoolTenant] = useState("");
  const [poolName, setPoolName] = useState("");
  const [poolId, setPoolId] = useState("");
  const [poolNumberId, setPoolNumberId] = useState("");
  const [canWrite, setCanWrite] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  async function load() {
    const [numberBody, poolBody] = await Promise.all([
      fetch("/api/admin/numbers", { credentials: "include" }).then((response) => response.json()),
      fetch("/api/admin/caller-id-pools", { credentials: "include" }).then((response) =>
        response.json(),
      ),
    ]);
    setNumbers((numberBody as { numbers?: NumberRow[] }).numbers ?? []);
    setPools((poolBody as { pools?: Pool[] }).pools ?? []);
  }

  useEffect(() => {
    let cancelled = false;
    async function run() {
      const [me, tenantBody] = await Promise.all([
        fetch("/api/auth/me", { credentials: "include" }).then((response) => response.json()),
        fetch("/api/admin/tenants", { credentials: "include" }).then((response) => response.json()),
      ]);
      if (cancelled) return;
      setCanWrite(Boolean((me as { can_write?: boolean }).can_write));
      const rows = (tenantBody as { tenants?: Tenant[] }).tenants ?? [];
      setTenants(rows);
      setTenantId(rows[0]?.id ?? "");
      setPoolTenant(rows[0]?.id ?? "");
      await load();
    }
    void run();
    return () => {
      cancelled = true;
    };
  }, []);

  async function importNumbers(event: FormEvent) {
    event.preventDefault();
    setError("");
    setNotice("");
    const values = paste
      .split(/[\s,]+/)
      .map((item) => item.trim())
      .filter(Boolean);
    const response = await fetch("/api/admin/numbers/import", {
      method: "POST",
      headers: { "content-type": "application/json" },
      credentials: "include",
      body: JSON.stringify({ numbers: values }),
    });
    const body = (await response.json()) as { detail?: string; imported?: string[]; skipped?: string[] };
    if (!response.ok) {
      setError(body.detail ?? "Could not import numbers");
      return;
    }
    setPaste("");
    setNotice(`Imported ${body.imported?.length ?? 0}. Skipped ${body.skipped?.length ?? 0}.`);
    await load();
  }

  async function assign(event: FormEvent) {
    event.preventDefault();
    setError("");
    const response = await fetch(`/api/admin/numbers/${assignId}`, {
      method: "PATCH",
      headers: { "content-type": "application/json" },
      credentials: "include",
      body: JSON.stringify({
        status: "assigned",
        tenant_id: tenantId,
        inbound_agent_id: agentId.trim() || null,
      }),
    });
    if (!response.ok) {
      const body = (await response.json()) as { detail?: string };
      setError(body.detail ?? "Could not assign the DID");
      return;
    }
    setAgentId("");
    await load();
  }

  async function setStatus(id: string, status: "free" | "blocked") {
    setError("");
    const response = await fetch(`/api/admin/numbers/${id}`, {
      method: "PATCH",
      headers: { "content-type": "application/json" },
      credentials: "include",
      body: JSON.stringify({ status }),
    });
    if (!response.ok) {
      const body = (await response.json()) as { detail?: string };
      setError(body.detail ?? "Could not update the DID");
      return;
    }
    await load();
  }

  async function createPool(event: FormEvent) {
    event.preventDefault();
    setError("");
    const response = await fetch("/api/admin/caller-id-pools", {
      method: "POST",
      headers: { "content-type": "application/json" },
      credentials: "include",
      body: JSON.stringify({ tenant_id: poolTenant, name: poolName }),
    });
    if (!response.ok) {
      const body = (await response.json()) as { detail?: string };
      setError(body.detail ?? "Could not create the pool");
      return;
    }
    setPoolName("");
    await load();
  }

  async function addToPool(event: FormEvent) {
    event.preventDefault();
    setError("");
    const response = await fetch(`/api/admin/caller-id-pools/${poolId}/numbers`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      credentials: "include",
      body: JSON.stringify({ phone_number_id: poolNumberId }),
    });
    if (!response.ok) {
      const body = (await response.json()) as { detail?: string };
      setError(body.detail ?? "Could not add the DID");
      return;
    }
    await load();
  }

  const assigned = numbers.filter((row) => row.status === "assigned");

  return (
    <div className="flex flex-col gap-6">
      <header>
        <h1 className="text-[32px] leading-none font-semibold tracking-[-0.8px]">Numbers</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Indian DIDs in E.164. Inbound dispatch reads the assigned tenant from here.
        </p>
      </header>
      <div className="overflow-x-auto rounded-2xl bg-white shadow-[0_0_0_1px_rgba(0,0,0,0.04)]">
        <table className="w-full min-w-[720px] text-left text-sm">
          <thead className="text-xs font-normal text-[#86868B]">
            <tr>
              <th className="px-3 py-2 font-medium">DID</th>
              <th className="px-3 py-2 font-medium">Status</th>
              <th className="px-3 py-2 font-medium">Tenant</th>
              <th className="px-3 py-2 font-medium">Pool</th>
              {canWrite ? <th className="px-3 py-2 font-medium">Actions</th> : null}
            </tr>
          </thead>
          <tbody>
            {numbers.map((row) => (
              <tr key={row.id} className="border-t border-border">
                <td className="px-3 py-2">{row.e164}</td>
                <td className="px-3 py-2">{row.status}</td>
                <td className="px-3 py-2">{row.tenant_name ?? "—"}</td>
                <td className="px-3 py-2">{row.pool_name ?? "—"}</td>
                {canWrite ? (
                  <td className="px-3 py-2">
                    <div className="flex gap-2">
                      <Button type="button" variant="outline" onClick={() => void setStatus(row.id, "free")}>
                        Free
                      </Button>
                      <Button type="button" variant="outline" onClick={() => void setStatus(row.id, "blocked")}>
                        Block
                      </Button>
                    </div>
                  </td>
                ) : null}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {canWrite ? (
        <div className="grid max-w-xl gap-8">
          <form className="grid gap-3" onSubmit={importNumbers}>
            <h2 className="text-lg font-semibold">Import</h2>
            <textarea
              className="min-h-24 rounded-lg border border-border bg-card px-3 py-2"
              value={paste}
              onChange={(event) => setPaste(event.target.value)}
              placeholder="+919876543210"
              required
            />
            <Button type="submit">Import DIDs</Button>
          </form>
          <form className="grid gap-3" onSubmit={assign}>
            <h2 className="text-lg font-semibold">Assign</h2>
            <select
              className="h-11 rounded-lg border border-border bg-card px-3"
              value={assignId}
              onChange={(event) => setAssignId(event.target.value)}
              required
            >
              <option value="">DID</option>
              {numbers.map((row) => (
                <option key={row.id} value={row.id}>
                  {row.e164}
                </option>
              ))}
            </select>
            <select
              className="h-11 rounded-lg border border-border bg-card px-3"
              value={tenantId}
              onChange={(event) => setTenantId(event.target.value)}
              required
            >
              {tenants.map((tenant) => (
                <option key={tenant.id} value={tenant.id}>
                  {tenant.name}
                </option>
              ))}
            </select>
            <input
              className="h-11 rounded-lg border border-border bg-card px-3"
              value={agentId}
              onChange={(event) => setAgentId(event.target.value)}
              placeholder="Inbound agent id (optional)"
            />
            <Button type="submit">Assign</Button>
          </form>
          <form className="grid gap-3" onSubmit={createPool}>
            <h2 className="text-lg font-semibold">Caller-ID pool</h2>
            <select
              className="h-11 rounded-lg border border-border bg-card px-3"
              value={poolTenant}
              onChange={(event) => setPoolTenant(event.target.value)}
            >
              {tenants.map((tenant) => (
                <option key={tenant.id} value={tenant.id}>
                  {tenant.name}
                </option>
              ))}
            </select>
            <input
              className="h-11 rounded-lg border border-border bg-card px-3"
              value={poolName}
              onChange={(event) => setPoolName(event.target.value)}
              placeholder="Pool name"
              required
            />
            <Button type="submit">Create pool</Button>
          </form>
          <form className="grid gap-3" onSubmit={addToPool}>
            <select
              className="h-11 rounded-lg border border-border bg-card px-3"
              value={poolId}
              onChange={(event) => setPoolId(event.target.value)}
              required
            >
              <option value="">Pool</option>
              {pools.map((pool) => (
                <option key={pool.id} value={pool.id}>
                  {pool.name}
                </option>
              ))}
            </select>
            <select
              className="h-11 rounded-lg border border-border bg-card px-3"
              value={poolNumberId}
              onChange={(event) => setPoolNumberId(event.target.value)}
              required
            >
              <option value="">Assigned DID</option>
              {assigned.map((row) => (
                <option key={row.id} value={row.id}>
                  {row.e164}
                </option>
              ))}
            </select>
            <Button type="submit">Add to pool</Button>
          </form>
        </div>
      ) : (
        <p className="text-sm text-muted-foreground">This role can view numbers and cannot change them.</p>
      )}
      {notice ? <p className="text-sm">{notice}</p> : null}
      {error ? <p className="text-sm text-destructive">{error}</p> : null}
    </div>
  );
}
