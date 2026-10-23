"use client";

import { useCallback, useEffect, useState, type FormEvent } from "react";
import { Button } from "@/components/ui/button";

type Tenant = {
  id: string;
  name: string;
  legal_name: string;
  gstin: string;
  contact_name: string;
  contact_email: string;
  contact_phone: string;
  status: string;
  plan: string | null;
  calls_allowed: boolean;
};

type Invite = { email: string; role: string; token: string };

const emptyForm = {
  name: "",
  legal_name: "",
  gstin: "",
  contact_name: "",
  contact_email: "",
  contact_phone: "",
  plan_name: "Starter",
};

export default function TenantsPage() {
  const [tenants, setTenants] = useState<Tenant[]>([]);
  const [plans, setPlans] = useState<string[]>(["Starter"]);
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState("");
  const [plan, setPlan] = useState("");
  const [form, setForm] = useState(emptyForm);
  const [editing, setEditing] = useState<string | null>(null);
  const [canWrite, setCanWrite] = useState(false);
  const [invite, setInvite] = useState<Invite | null>(null);
  const [concurrency, setConcurrency] = useState("");
  const [minuteRate, setMinuteRate] = useState("");
  const [transferRate, setTransferRate] = useState("");
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    const params = new URLSearchParams();
    if (query) params.set("q", query);
    if (status) params.set("status", status);
    if (plan) params.set("plan", plan);
    const response = await fetch(`/api/admin/tenants?${params}`, { credentials: "include" });
    if (!response.ok) {
      setError("Could not load tenants");
      return;
    }
    const body = (await response.json()) as { tenants: Tenant[] };
    setTenants(body.tenants);
  }, [query, status, plan]);

  useEffect(() => {
    void fetch("/api/auth/me", { credentials: "include" })
      .then((response) => response.json())
      .then((body: { can_write?: boolean }) => setCanWrite(Boolean(body.can_write)));
    void fetch("/api/admin/plans", { credentials: "include" })
      .then((response) => response.json())
      .then((body: { plans?: { name: string }[] }) => {
        if (body.plans?.length) setPlans(body.plans.map((item) => item.name));
      });
  }, []);

  useEffect(() => {
    let cancelled = false;
    async function run() {
      const params = new URLSearchParams();
      if (query) params.set("q", query);
      if (status) params.set("status", status);
      if (plan) params.set("plan", plan);
      const response = await fetch(`/api/admin/tenants?${params}`, { credentials: "include" });
      if (!response.ok || cancelled) return;
      const body = (await response.json()) as { tenants: Tenant[] };
      if (!cancelled) setTenants(body.tenants);
    }
    void run();
    return () => {
      cancelled = true;
    };
  }, [query, status, plan]);

  function setField(key: keyof typeof emptyForm, value: string) {
    setForm((current) => ({ ...current, [key]: value }));
  }

  async function save(event: FormEvent) {
    event.preventDefault();
    setError("");
    const response = await fetch(editing ? `/api/admin/tenants/${editing}` : "/api/admin/tenants", {
      method: editing ? "PATCH" : "POST",
      headers: { "content-type": "application/json" },
      credentials: "include",
      body: JSON.stringify(form),
    });
    const body = (await response.json()) as { detail?: string; invite?: Invite };
    if (!response.ok) {
      setError(body.detail ?? "Could not save the tenant");
      return;
    }
    if (editing) {
      const limits = await fetch(`/api/admin/tenants/${editing}/limits`, {
        method: "PUT",
        headers: { "content-type": "application/json" },
        credentials: "include",
        body: JSON.stringify({
          max_concurrent_calls: concurrency === "" ? null : Number(concurrency),
          per_minute_rate_paise: minuteRate === "" ? null : Number(minuteRate),
          transfer_leg_rate_paise: transferRate === "" ? null : Number(transferRate),
        }),
      });
      if (!limits.ok) {
        setError("Tenant saved, but the limit override failed");
        await load();
        return;
      }
    }
    setInvite(body.invite ?? null);
    setEditing(null);
    setForm(emptyForm);
    setConcurrency("");
    setMinuteRate("");
    setTransferRate("");
    await load();
  }

  async function setTenantStatus(id: string, next: "suspend" | "reactivate") {
    setError("");
    const response = await fetch(`/api/admin/tenants/${id}/${next}`, {
      method: "POST",
      credentials: "include",
    });
    if (!response.ok) {
      setError("Could not update the tenant");
      return;
    }
    await load();
  }

  return (
    <div className="flex flex-col gap-6">
      <header>
        <h1 className="text-2xl font-semibold">Tenants</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Create a workspace, then suspend it to block sign-in and new calls.
        </p>
      </header>
      {invite ? (
        <p className="break-all rounded-lg border border-border bg-card p-3 text-sm">
          Tenant Admin invite for {invite.email}. Token (shown once): {invite.token}
        </p>
      ) : null}
      <form className="flex flex-wrap gap-2" onSubmit={(event) => event.preventDefault()}>
        <input
          className="h-10 rounded-lg border border-border bg-card px-3 text-sm"
          placeholder="Search name, legal entity, GSTIN"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          aria-label="Search tenants"
        />
        <select
          className="h-10 rounded-lg border border-border bg-card px-3 text-sm"
          value={status}
          onChange={(event) => setStatus(event.target.value)}
          aria-label="Status"
        >
          <option value="">Any status</option>
          <option value="active">Active</option>
          <option value="suspended">Suspended</option>
        </select>
        <select
          className="h-10 rounded-lg border border-border bg-card px-3 text-sm"
          value={plan}
          onChange={(event) => setPlan(event.target.value)}
          aria-label="Plan"
        >
          <option value="">Any plan</option>
          {plans.map((name) => (
            <option key={name} value={name}>
              {name}
            </option>
          ))}
        </select>
      </form>
      <div className="overflow-x-auto rounded-lg border border-border">
        <table className="w-full min-w-[720px] text-left text-sm">
          <thead className="bg-card text-muted-foreground">
            <tr>
              <th className="px-3 py-2 font-medium">Name</th>
              <th className="px-3 py-2 font-medium">Plan</th>
              <th className="px-3 py-2 font-medium">Status</th>
              <th className="px-3 py-2 font-medium">Calls</th>
              <th className="px-3 py-2 font-medium">Contact</th>
              {canWrite ? <th className="px-3 py-2 font-medium">Actions</th> : null}
            </tr>
          </thead>
          <tbody>
            {tenants.map((tenant) => (
              <tr key={tenant.id} className="border-t border-border">
                <td className="px-3 py-2">
                  <div className="font-medium">{tenant.name}</div>
                  <div className="text-muted-foreground">{tenant.legal_name}</div>
                </td>
                <td className="px-3 py-2">{tenant.plan}</td>
                <td className="px-3 py-2">{tenant.status}</td>
                <td className="px-3 py-2">{tenant.calls_allowed ? "Allowed" : "Blocked"}</td>
                <td className="px-3 py-2">{tenant.contact_email}</td>
                {canWrite ? (
                  <td className="px-3 py-2">
                    <div className="flex gap-2">
                      <Button
                        type="button"
                        variant="outline"
                        onClick={() => {
                          setEditing(tenant.id);
                          setConcurrency("");
                          setMinuteRate("");
                          setTransferRate("");
                          void fetch(`/api/admin/tenants/${tenant.id}/limits`, {
                            credentials: "include",
                          })
                            .then((response) => response.json())
                            .then(
                              (limits: {
                                overrides?: {
                                  max_concurrent_calls: number | null;
                                  per_minute_rate_paise: number | null;
                                  transfer_leg_rate_paise: number | null;
                                };
                              }) => {
                                const overrides = limits.overrides;
                                if (!overrides) return;
                                setConcurrency(
                                  overrides.max_concurrent_calls == null
                                    ? ""
                                    : String(overrides.max_concurrent_calls),
                                );
                                setMinuteRate(
                                  overrides.per_minute_rate_paise == null
                                    ? ""
                                    : String(overrides.per_minute_rate_paise),
                                );
                                setTransferRate(
                                  overrides.transfer_leg_rate_paise == null
                                    ? ""
                                    : String(overrides.transfer_leg_rate_paise),
                                );
                              },
                            );
                          setForm({
                            name: tenant.name,
                            legal_name: tenant.legal_name,
                            gstin: tenant.gstin,
                            contact_name: tenant.contact_name,
                            contact_email: tenant.contact_email,
                            contact_phone: tenant.contact_phone,
                            plan_name: tenant.plan ?? "Starter",
                          });
                        }}
                      >
                        Edit
                      </Button>
                      <Button
                        type="button"
                        variant="outline"
                        onClick={() =>
                          void setTenantStatus(
                            tenant.id,
                            tenant.status === "suspended" ? "reactivate" : "suspend",
                          )
                        }
                      >
                        {tenant.status === "suspended" ? "Reactivate" : "Suspend"}
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
        <form className="grid max-w-xl gap-3" onSubmit={save}>
          <h2 className="text-lg font-semibold">{editing ? "Edit tenant" : "New tenant"}</h2>
          {(
            [
              ["name", "Name"],
              ["legal_name", "Legal entity"],
              ["gstin", "GSTIN"],
              ["contact_name", "Contact name"],
              ["contact_email", "Contact email"],
              ["contact_phone", "Contact phone"],
            ] as const
          ).map(([key, label]) => (
            <label key={key} className="flex flex-col gap-1 text-sm">
              {label}
              <input
                className="h-11 rounded-lg border border-border bg-card px-3"
                value={form[key]}
                onChange={(event) => setField(key, event.target.value)}
                required={key !== "gstin" && key !== "contact_phone"}
              />
            </label>
          ))}
          <label className="flex flex-col gap-1 text-sm">
            Plan
            <select
              className="h-11 rounded-lg border border-border bg-card px-3"
              value={form.plan_name}
              onChange={(event) => setField("plan_name", event.target.value)}
            >
              {plans.map((name) => (
                <option key={name} value={name}>
                  {name}
                </option>
              ))}
            </select>
          </label>
          {editing ? (
            <div className="grid gap-3 rounded-lg border border-border p-3">
              <h3 className="text-sm font-semibold">Limit overrides</h3>
              <p className="text-sm text-muted-foreground">
                Leave a field empty to use the plan. Rates are in paise.
              </p>
              <label className="flex flex-col gap-1 text-sm">
                Max concurrent calls
                <input
                  className="h-11 rounded-lg border border-border bg-card px-3"
                  inputMode="numeric"
                  value={concurrency}
                  onChange={(event) => setConcurrency(event.target.value)}
                />
              </label>
              <label className="flex flex-col gap-1 text-sm">
                Per-minute rate (paise)
                <input
                  className="h-11 rounded-lg border border-border bg-card px-3"
                  inputMode="numeric"
                  value={minuteRate}
                  onChange={(event) => setMinuteRate(event.target.value)}
                />
              </label>
              <label className="flex flex-col gap-1 text-sm">
                Transfer-leg rate (paise)
                <input
                  className="h-11 rounded-lg border border-border bg-card px-3"
                  inputMode="numeric"
                  value={transferRate}
                  onChange={(event) => setTransferRate(event.target.value)}
                />
              </label>
            </div>
          ) : null}
          <Button type="submit">{editing ? "Save changes" : "Create tenant"}</Button>
        </form>
      ) : (
        <p className="text-sm text-muted-foreground">This role can view tenants and cannot change them.</p>
      )}
      {error ? <p className="text-sm text-destructive">{error}</p> : null}
    </div>
  );
}
