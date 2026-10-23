"use client";

import { useEffect, useState, type FormEvent } from "react";
import { Button } from "@/components/ui/button";

type Tenant = { id: string; name: string };

export function PlatformControls() {
  const [tenants, setTenants] = useState<Tenant[]>([]);
  const [tenantId, setTenantId] = useState("");
  const [reason, setReason] = useState("");
  const [globalOn, setGlobalOn] = useState(false);
  const [canWrite, setCanWrite] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    async function run() {
      const [me, tenantBody, kill] = await Promise.all([
        fetch("/api/auth/me", { credentials: "include" }).then((response) => response.json()),
        fetch("/api/admin/tenants", { credentials: "include" }).then((response) => response.json()),
        fetch("/api/admin/kill-switch", { credentials: "include" }).then((response) => response.json()),
      ]);
      if (cancelled) return;
      setCanWrite(Boolean((me as { can_write?: boolean }).can_write));
      const rows = (tenantBody as { tenants?: Tenant[] }).tenants ?? [];
      setTenants(rows);
      setTenantId(rows[0]?.id ?? "");
      setGlobalOn(Boolean((kill as { global?: boolean }).global));
    }
    void run();
    return () => {
      cancelled = true;
    };
  }, []);

  async function toggleGlobal() {
    setError("");
    const response = await fetch("/api/admin/kill-switch", {
      method: "PUT",
      headers: { "content-type": "application/json" },
      credentials: "include",
      body: JSON.stringify({ scope: "global", enabled: !globalOn }),
    });
    if (!response.ok) {
      setError("Could not change the kill switch");
      return;
    }
    setGlobalOn(!globalOn);
  }

  async function impersonate(event: FormEvent) {
    event.preventDefault();
    setError("");
    const response = await fetch("/api/admin/impersonate", {
      method: "POST",
      headers: { "content-type": "application/json" },
      credentials: "include",
      body: JSON.stringify({ tenant_id: tenantId, reason }),
    });
    if (!response.ok) {
      const body = (await response.json()) as { detail?: string };
      setError(body.detail ?? "Could not start impersonation");
      return;
    }
    window.location.reload();
  }

  return (
    <section className="flex flex-col gap-4 rounded-lg border border-border p-4">
      <h2 className="text-lg font-semibold">Controls</h2>
      <div className="flex items-center justify-between gap-3">
        <p className="text-sm">
          Global outbound kill switch is {globalOn ? "on. New outbound calls are stopped." : "off."}
        </p>
        {canWrite ? (
          <Button type="button" variant="outline" onClick={() => void toggleGlobal()}>
            {globalOn ? "Turn off" : "Stop outbound"}
          </Button>
        ) : null}
      </div>
      {canWrite ? (
        <form className="grid max-w-xl gap-3" onSubmit={impersonate}>
          <h3 className="text-sm font-medium">Impersonate a tenant</h3>
          <select
            className="h-11 rounded-lg border border-border bg-card px-3"
            aria-label="Tenant to impersonate"
            value={tenantId}
            onChange={(event) => setTenantId(event.target.value)}
          >
            {tenants.map((tenant) => (
              <option key={tenant.id} value={tenant.id}>
                {tenant.name}
              </option>
            ))}
          </select>
          <input
            className="h-11 rounded-lg border border-border bg-card px-3"
            aria-label="Reason"
            value={reason}
            onChange={(event) => setReason(event.target.value)}
            placeholder="Reason (required)"
            required
            minLength={10}
          />
          <Button type="submit">Impersonate for 30 minutes</Button>
        </form>
      ) : null}
      {error ? <p className="text-sm text-destructive">{error}</p> : null}
    </section>
  );
}
