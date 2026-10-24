"use client";

import { useEffect, useState, type FormEvent, type ReactNode } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";

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
  created_at: string;
};

type Limits = {
  per_minute_rate_paise: number;
  transfer_leg_rate_paise: number;
  max_concurrent_calls: number;
  max_agents: number;
  overrides: {
    max_concurrent_calls: number | null;
    per_minute_rate_paise: number | null;
    transfer_leg_rate_paise: number | null;
  };
};

type Did = { id: string; e164: string; status: string };
type AgentRow = { id: string; name: string; deployed: boolean; created_at: string };
type CallRow = { id: string; agent_name: string; created_at: string };
type UserRow = { id: string; email: string; full_name: string; disabled: boolean; roles: string[] };

const TABS = [
  ["overview", "Overview"],
  ["calls", "Calls"],
  ["agents", "Agents"],
  ["numbers", "Numbers"],
  ["billing", "Billing"],
  ["users", "Users"],
] as const;

const BILLS = [
  ["plan", "Plan"],
  ["ledger", "Ledger"],
  ["credits", "Credits"],
  ["receipts", "Receipts"],
  ["invoices", "Invoices"],
] as const;

const ROLES = ["Tenant Admin", "Manager", "Agent Builder", "Human Agent", "Viewer"];

const field =
  "h-10 w-full rounded-lg border border-[#E8E8ED] bg-white px-3 text-sm text-[#1D1D1F] outline-none focus:border-[#1D1D1F]";

function rupees(paise: number | null | undefined) {
  if (paise == null) return "—";
  return new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency: "INR",
    maximumFractionDigits: 2,
  }).format(paise / 100);
}

function when(iso: string) {
  return new Date(iso).toLocaleString("en-IN", {
    timeZone: "Asia/Kolkata",
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "numeric",
    minute: "2-digit",
    hour12: true,
  });
}

function blank(value: number | null | undefined) {
  return value == null ? "" : String(value);
}

export function TenantProfile({ id }: { id: string }) {
  const router = useRouter();
  const params = useSearchParams();
  const tab = TABS.some(([key]) => key === params.get("tab")) ? (params.get("tab") as (typeof TABS)[number][0]) : "overview";
  const bill = BILLS.some(([key]) => key === params.get("bill"))
    ? (params.get("bill") as (typeof BILLS)[number][0])
    : "plan";

  const [tenant, setTenant] = useState<Tenant | null>(null);
  const [missing, setMissing] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [canWrite, setCanWrite] = useState(false);
  const [plans, setPlans] = useState<string[]>(["Starter"]);
  const [limits, setLimits] = useState<Limits | null>(null);
  const [numbers, setNumbers] = useState<Did[]>([]);
  const [freeNumbers, setFreeNumbers] = useState<Did[]>([]);
  const [agents, setAgents] = useState<AgentRow[]>([]);
  const [calls, setCalls] = useState<CallRow[]>([]);
  const [users, setUsers] = useState<UserRow[]>([]);
  const [outboundStopped, setOutboundStopped] = useState(false);
  const [revision, setRevision] = useState(0);

  const [form, setForm] = useState({
    name: "",
    legal_name: "",
    gstin: "",
    contact_name: "",
    contact_email: "",
    contact_phone: "",
    plan_name: "Starter",
  });
  const [concurrency, setConcurrency] = useState("");
  const [minuteRate, setMinuteRate] = useState("");
  const [transferRate, setTransferRate] = useState("");
  const [reasonOpen, setReasonOpen] = useState(false);
  const [reason, setReason] = useState("");
  const [agentName, setAgentName] = useState("");
  const [assignId, setAssignId] = useState("");
  const [invite, setInvite] = useState({ full_name: "", email: "", role_name: "Tenant Admin" });
  const [token, setToken] = useState("");

  useEffect(() => {
    let cancelled = false;
    async function run() {
      const [me, list, planList] = await Promise.all([
        fetch("/api/auth/me", { credentials: "include" }).then((response) => response.json()),
        fetch("/api/admin/tenants", { credentials: "include" }).then((response) => response.json()),
        fetch("/api/admin/plans", { credentials: "include" }).then((response) => response.json()),
      ]);
      if (cancelled) return;
      setCanWrite(Boolean((me as { can_write?: boolean }).can_write));
      const names = ((planList as { plans?: { name: string }[] }).plans ?? []).map((item) => item.name);
      if (names.length) setPlans(names);
      const found = ((list as { tenants?: Tenant[] }).tenants ?? []).find((item) => item.id === id) ?? null;
      if (!found) {
        setMissing(true);
        setTenant(null);
        return;
      }
      setMissing(false);
      setTenant(found);
      setForm({
        name: found.name,
        legal_name: found.legal_name,
        gstin: found.gstin,
        contact_name: found.contact_name,
        contact_email: found.contact_email,
        contact_phone: found.contact_phone,
        plan_name: found.plan ?? "Starter",
      });
      const [limitBody, numberBody, freeBody, userBody, agentBody, callBody, killBody] = await Promise.all([
        fetch(`/api/admin/tenants/${id}/limits`, { credentials: "include" }).then((response) => response.json()),
        fetch(`/api/admin/numbers?tenant_id=${id}`, { credentials: "include" }).then((response) => response.json()),
        fetch("/api/admin/numbers?status=free", { credentials: "include" }).then((response) => response.json()),
        fetch(`/api/admin/users?tenant_id=${id}`, { credentials: "include" }).then((response) => response.json()),
        fetch(`/api/admin/agents?tenant_id=${id}`, { credentials: "include" }).then((response) => response.json()),
        fetch(`/api/admin/calls?tenant_id=${id}`, { credentials: "include" }).then((response) => response.json()),
        fetch(`/api/admin/kill-switch?tenant_id=${id}`, { credentials: "include" }).then((response) => response.json()),
      ]);
      if (cancelled) return;
      const nextLimits = limitBody as Limits;
      if (nextLimits.overrides) {
        setLimits(nextLimits);
        setConcurrency(blank(nextLimits.overrides.max_concurrent_calls));
        setMinuteRate(blank(nextLimits.overrides.per_minute_rate_paise));
        setTransferRate(blank(nextLimits.overrides.transfer_leg_rate_paise));
      }
      setNumbers((numberBody as { numbers?: Did[] }).numbers ?? []);
      setFreeNumbers((freeBody as { numbers?: Did[] }).numbers ?? []);
      setUsers((userBody as { users?: UserRow[] }).users ?? []);
      setAgents((agentBody as { agents?: AgentRow[] }).agents ?? []);
      setCalls((callBody as { calls?: CallRow[] }).calls ?? []);
      const kill = killBody as { global?: boolean; tenant?: boolean | null };
      setOutboundStopped(Boolean(kill.global || kill.tenant));
    }
    void run().catch(() => {
      if (!cancelled) setError("Could not load this account");
    });
    return () => {
      cancelled = true;
    };
  }, [id, revision]);

  function openTab(next: string, nextBill?: string) {
    const search = new URLSearchParams(params.toString());
    search.set("tab", next);
    if (nextBill) search.set("bill", nextBill);
    if (next !== "billing") search.delete("bill");
    router.replace(`/admin/tenants/${id}?${search}`);
  }

  function setField(key: keyof typeof form, value: string) {
    setForm((current) => ({ ...current, [key]: value }));
  }

  async function saveIdentity(event?: FormEvent) {
    event?.preventDefault();
    setError("");
    setNotice("");
    const response = await fetch(`/api/admin/tenants/${id}`, {
      method: "PATCH",
      headers: { "content-type": "application/json" },
      credentials: "include",
      body: JSON.stringify(form),
    });
    if (!response.ok) {
      const body = (await response.json()) as { detail?: string };
      setError(body.detail ?? "Could not save this account");
      return;
    }
    setNotice("Saved");
    setRevision((current) => current + 1);
  }

  async function setStatus(next: "suspend" | "reactivate") {
    setError("");
    const response = await fetch(`/api/admin/tenants/${id}/${next}`, {
      method: "POST",
      credentials: "include",
    });
    if (!response.ok) {
      setError("Could not update the account status");
      return;
    }
    setRevision((current) => current + 1);
  }

  async function setOutbound(stopped: boolean) {
    setError("");
    const response = await fetch("/api/admin/kill-switch", {
      method: "PUT",
      headers: { "content-type": "application/json" },
      credentials: "include",
      body: JSON.stringify({ scope: "tenant", tenant_id: id, enabled: stopped }),
    });
    if (!response.ok) {
      setError("Could not update outbound");
      return;
    }
    setRevision((current) => current + 1);
  }

  async function saveRates(event: FormEvent) {
    event.preventDefault();
    setError("");
    const response = await fetch(`/api/admin/tenants/${id}/limits`, {
      method: "PUT",
      headers: { "content-type": "application/json" },
      credentials: "include",
      body: JSON.stringify({
        max_concurrent_calls: concurrency === "" ? null : Number(concurrency),
        per_minute_rate_paise: minuteRate === "" ? null : Number(minuteRate),
        transfer_leg_rate_paise: transferRate === "" ? null : Number(transferRate),
      }),
    });
    if (!response.ok) {
      setError("Could not save the rates");
      return;
    }
    setNotice("Rates saved");
    setRevision((current) => current + 1);
  }

  async function impersonate(event: FormEvent) {
    event.preventDefault();
    setError("");
    const response = await fetch("/api/admin/impersonate", {
      method: "POST",
      headers: { "content-type": "application/json" },
      credentials: "include",
      body: JSON.stringify({ tenant_id: id, reason }),
    });
    if (!response.ok) {
      const body = (await response.json()) as { detail?: string };
      setError(body.detail ?? "Could not open this account");
      return;
    }
    window.location.reload();
  }

  async function addAgent(event: FormEvent) {
    event.preventDefault();
    setError("");
    const response = await fetch("/api/admin/agents", {
      method: "POST",
      headers: { "content-type": "application/json" },
      credentials: "include",
      body: JSON.stringify({ tenant_id: id, name: agentName }),
    });
    if (!response.ok) {
      setError("Could not create the agent");
      return;
    }
    setAgentName("");
    setRevision((current) => current + 1);
  }

  async function assignNumber(event: FormEvent) {
    event.preventDefault();
    if (!assignId) return;
    setError("");
    const response = await fetch(`/api/admin/numbers/${assignId}`, {
      method: "PATCH",
      headers: { "content-type": "application/json" },
      credentials: "include",
      body: JSON.stringify({ status: "assigned", tenant_id: id, inbound_agent_id: null }),
    });
    if (!response.ok) {
      setError("Could not assign that number");
      return;
    }
    setAssignId("");
    setRevision((current) => current + 1);
  }

  async function inviteUser(event: FormEvent) {
    event.preventDefault();
    setError("");
    setToken("");
    const response = await fetch("/api/admin/users", {
      method: "POST",
      headers: { "content-type": "application/json" },
      credentials: "include",
      body: JSON.stringify({ ...invite, tenant_id: id }),
    });
    const body = (await response.json()) as { detail?: string; invite?: { token: string } };
    if (!response.ok) {
      setError(typeof body.detail === "string" ? body.detail : "Could not invite this person");
      return;
    }
    setToken(body.invite?.token ?? "");
    setInvite({ full_name: "", email: "", role_name: "Tenant Admin" });
    setRevision((current) => current + 1);
  }

  if (missing) {
    return (
      <div className="flex flex-col gap-3">
        <Link href="/admin/tenants" className="text-sm text-[#6E6E73] no-underline">
          ← Tenants
        </Link>
        <p className="text-sm text-[#6E6E73]">This account is not on the platform.</p>
      </div>
    );
  }

  if (!tenant) {
    return <p className="text-sm text-[#6E6E73]">{error || "Loading account…"}</p>;
  }

  const tiles = [
    { label: "Recent calls", value: String(calls.length) },
    { label: "Numbers", value: String(numbers.length) },
    { label: "Agents", value: String(agents.length) },
    { label: "Per minute", value: limits ? rupees(limits.per_minute_rate_paise) : "—" },
    { label: "Outbound", value: outboundStopped ? "Stopped" : "Allowed" },
  ];

  return (
    <div className="flex flex-col gap-5">
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div className="flex min-w-0 items-start gap-3">
          <Link
            href="/admin/tenants"
            aria-label="Back to tenants"
            className="mt-1 flex size-8 items-center justify-center rounded-full text-lg text-[#1D1D1F] no-underline hover:bg-white"
          >
            ←
          </Link>
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <h1 className="text-[28px] leading-none font-semibold tracking-[-0.6px]">{tenant.name}</h1>
              <StatusPill status={tenant.status} />
            </div>
            <p className="mt-2 text-sm text-[#6E6E73]">
              {tenant.contact_email}
              {tenant.plan ? ` · ${tenant.plan}` : ""}
            </p>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {canWrite ? (
            <button
              type="button"
              className="h-9 rounded-full border border-[#D2D2D7] bg-white px-4 text-sm"
              onClick={() => setReasonOpen((open) => !open)}
            >
              Impersonate
            </button>
          ) : null}
          {canWrite ? (
            <button
              type="button"
              className="h-9 rounded-full bg-[#1D1D1F] px-4 text-sm font-medium text-white"
              onClick={() => void saveIdentity()}
            >
              Save changes
            </button>
          ) : null}
        </div>
      </header>

      {reasonOpen ? (
        <form
          className="flex flex-wrap items-end gap-2 rounded-2xl bg-white p-4 shadow-[0_0_0_1px_rgba(0,0,0,0.04)]"
          onSubmit={impersonate}
        >
          <label className="flex min-w-[280px] flex-1 flex-col gap-1.5 text-sm">
            <span className="text-[#6E6E73]">Reason. At least 10 characters. Logged for 30 minutes.</span>
            <input className={field} value={reason} onChange={(event) => setReason(event.target.value)} required minLength={10} />
          </label>
          <button type="submit" className="h-10 rounded-full bg-[#1D1D1F] px-4 text-sm font-medium text-white">
            Open as tenant
          </button>
        </form>
      ) : null}

      <section aria-label="Account numbers" className="grid grid-cols-[repeat(auto-fit,minmax(160px,1fr))] gap-3">
        {tiles.map((tile) => (
          <div
            key={tile.label}
            className="flex flex-col gap-1 rounded-2xl bg-white px-4 pt-4 pb-3 shadow-[0_0_0_1px_rgba(0,0,0,0.04)]"
          >
            <span className="text-[13px] text-[#6E6E73]">{tile.label}</span>
            <span className="text-[26px] font-semibold tracking-[-0.5px] tabular-nums">{tile.value}</span>
          </div>
        ))}
      </section>

      <nav className="flex gap-5 border-b border-[#E8E8ED]" aria-label="Account">
        {TABS.map(([key, label]) => (
          <button
            key={key}
            type="button"
            className="border-b-2 pb-2 text-sm"
            style={{
              borderColor: tab === key ? "#1D1D1F" : "transparent",
              color: tab === key ? "#1D1D1F" : "#6E6E73",
              fontWeight: tab === key ? 600 : 400,
            }}
            onClick={() => openTab(key, key === "billing" ? bill : undefined)}
          >
            {label}
          </button>
        ))}
      </nav>

      {error ? <p className="text-sm text-[#D70015]">{error}</p> : null}
      {notice ? <p className="text-sm text-[#248A3D]">{notice}</p> : null}

      {tab === "overview" ? (
        <div className="flex flex-col gap-4">
          <Card title="Account status">
            <div className="grid gap-4 md:grid-cols-3">
              <label className="flex flex-col gap-1.5 text-sm">
                <span className="text-[#6E6E73]">Account status</span>
                <select
                  className={field}
                  value={tenant.status}
                  disabled={!canWrite}
                  onChange={(event) =>
                    void setStatus(event.target.value === "suspended" ? "suspend" : "reactivate")
                  }
                >
                  <option value="active">Active</option>
                  <option value="suspended">Suspended</option>
                </select>
              </label>
              <label className="flex flex-col gap-1.5 text-sm">
                <span className="text-[#6E6E73]">Outbound</span>
                <select
                  className={field}
                  value={outboundStopped ? "stopped" : "allowed"}
                  disabled={!canWrite}
                  onChange={(event) => void setOutbound(event.target.value === "stopped")}
                >
                  <option value="allowed">Allowed</option>
                  <option value="stopped">Stopped</option>
                </select>
              </label>
              <label className="flex flex-col gap-1.5 text-sm">
                <span className="text-[#6E6E73]">Plan</span>
                <select
                  className={field}
                  value={form.plan_name}
                  disabled={!canWrite}
                  onChange={(event) => setField("plan_name", event.target.value)}
                >
                  {plans.map((name) => (
                    <option key={name} value={name}>
                      {name}
                    </option>
                  ))}
                </select>
              </label>
            </div>
            <p className="mt-3 text-[13px] text-[#86868B]">
              Plan changes save with Save changes. Outbound stop is this account only.
            </p>
          </Card>

          <Card title="Identity">
            <form className="grid gap-4 md:grid-cols-2" onSubmit={saveIdentity}>
              {(
                [
                  ["name", "Name"],
                  ["legal_name", "Legal entity"],
                  ["contact_name", "Contact name"],
                  ["contact_email", "Contact email"],
                  ["contact_phone", "Contact phone"],
                  ["gstin", "GSTIN"],
                ] as const
              ).map(([key, label]) => (
                <label key={key} className="flex flex-col gap-1.5 text-sm">
                  <span className="text-[#6E6E73]">{label}</span>
                  <input
                    className={field}
                    value={form[key]}
                    disabled={!canWrite}
                    onChange={(event) => setField(key, event.target.value)}
                    required={key !== "gstin" && key !== "contact_phone"}
                  />
                </label>
              ))}
            </form>
          </Card>
        </div>
      ) : null}

      {tab === "calls" ? (
        <Card title="Calls" aside={`${calls.length} shown`}>
          <Table
            columns={["Date", "Agent", "Call"]}
            empty="No calls for this account yet."
            rows={calls.map((call) => [when(call.created_at), call.agent_name, call.id.slice(0, 8)])}
          />
        </Card>
      ) : null}

      {tab === "agents" ? (
        <div className="flex flex-col gap-4">
          {canWrite ? (
            <form className="flex flex-wrap items-end gap-2" onSubmit={addAgent}>
              <label className="flex min-w-[220px] flex-1 flex-col gap-1.5 text-sm">
                <span className="text-[#6E6E73]">New agent</span>
                <input
                  className={field}
                  value={agentName}
                  onChange={(event) => setAgentName(event.target.value)}
                  required
                />
              </label>
              <button type="submit" className="h-10 rounded-full bg-[#1D1D1F] px-4 text-sm font-medium text-white">
                Create
              </button>
            </form>
          ) : null}
          <Card title="Agents">
            <Table
              columns={["Name", "Status", "Created"]}
              empty="No agents on this account."
              rows={agents.map((agent) => [
                agent.name,
                agent.deployed ? "Live" : "Draft",
                when(agent.created_at),
              ])}
            />
          </Card>
        </div>
      ) : null}

      {tab === "numbers" ? (
        <div className="flex flex-col gap-4">
          {canWrite ? (
            <form className="flex flex-wrap items-end gap-2" onSubmit={assignNumber}>
              <label className="flex min-w-[220px] flex-1 flex-col gap-1.5 text-sm">
                <span className="text-[#6E6E73]">Assign a free number</span>
                <select className={field} value={assignId} onChange={(event) => setAssignId(event.target.value)}>
                  <option value="">Choose a DID</option>
                  {freeNumbers.map((number) => (
                    <option key={number.id} value={number.id}>
                      {number.e164}
                    </option>
                  ))}
                </select>
              </label>
              <button type="submit" className="h-10 rounded-full bg-[#1D1D1F] px-4 text-sm font-medium text-white">
                Assign
              </button>
              <Link href="/admin/numbers" className="mb-2 text-sm text-[#6E6E73] no-underline">
                Number inventory
              </Link>
            </form>
          ) : null}
          <Card title="Numbers">
            <Table
              columns={["Number", "Status"]}
              empty="No numbers on this account."
              rows={numbers.map((number) => [number.e164, number.status])}
            />
          </Card>
        </div>
      ) : null}

      {tab === "billing" ? (
        <div className="flex flex-col gap-4">
          <nav className="flex gap-4" aria-label="Billing">
            {BILLS.map(([key, label]) => (
              <button
                key={key}
                type="button"
                className="border-b-2 pb-1 text-sm"
                style={{
                  borderColor: bill === key ? "#1D1D1F" : "transparent",
                  color: bill === key ? "#1D1D1F" : "#6E6E73",
                }}
                onClick={() => openTab("billing", key)}
              >
                {label}
              </button>
            ))}
          </nav>

          {bill === "plan" ? (
            <div className="flex flex-col gap-4">
              <Card title="Current plan">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <p className="text-[17px] font-semibold">{tenant.plan ?? "No plan"}</p>
                    <p className="mt-1 text-sm text-[#6E6E73]">
                      {limits
                        ? `${rupees(limits.per_minute_rate_paise)} / minute · ${limits.max_concurrent_calls} concurrent · ${limits.max_agents} agents`
                        : "Rates load with the plan."}
                    </p>
                  </div>
                  <StatusPill status={tenant.status} />
                </div>
              </Card>
              <Card title="Rates for this account">
                <form className="grid gap-4 md:grid-cols-3" onSubmit={saveRates}>
                  <label className="flex flex-col gap-1.5 text-sm">
                    <span className="text-[#6E6E73]">Per minute (paise)</span>
                    <input className={field} inputMode="numeric" value={minuteRate} disabled={!canWrite} onChange={(event) => setMinuteRate(event.target.value)} />
                  </label>
                  <label className="flex flex-col gap-1.5 text-sm">
                    <span className="text-[#6E6E73]">Transfer leg (paise)</span>
                    <input className={field} inputMode="numeric" value={transferRate} disabled={!canWrite} onChange={(event) => setTransferRate(event.target.value)} />
                  </label>
                  <label className="flex flex-col gap-1.5 text-sm">
                    <span className="text-[#6E6E73]">Max concurrent calls</span>
                    <input className={field} inputMode="numeric" value={concurrency} disabled={!canWrite} onChange={(event) => setConcurrency(event.target.value)} />
                  </label>
                  <p className="text-[13px] text-[#86868B] md:col-span-3">
                    Leave a field empty to use the plan.
                    {limits ? ` Effective transfer leg ${rupees(limits.transfer_leg_rate_paise)}.` : ""}
                  </p>
                  {canWrite ? (
                    <button type="submit" className="h-10 w-fit rounded-full bg-[#1D1D1F] px-4 text-sm font-medium text-white">
                      Save rates
                    </button>
                  ) : null}
                </form>
              </Card>
            </div>
          ) : null}

          {bill === "ledger" ? (
            <Card title="Ledger" aside="Wallet not connected">
              <Table
                columns={["Date", "Direction", "Source", "Amount", "Balance after", "Reason"]}
                empty="No wallet entries yet. Call charges post here once the prepaid wallet is connected."
                rows={[]}
              />
            </Card>
          ) : null}
          {bill === "credits" ? (
            <Card title="Credits" aside="Wallet not connected">
              <Table
                columns={["Amount", "Type", "Expires", "Notes"]}
                empty="No credits issued. Credits post here once the wallet is connected."
                rows={[]}
              />
            </Card>
          ) : null}
          {bill === "receipts" ? (
            <Card title="Receipts" aside="Wallet not connected">
              <Table
                columns={["Date", "Receipt", "Event", "Amount", "Wallet"]}
                empty="No receipts yet."
                rows={[]}
              />
            </Card>
          ) : null}
          {bill === "invoices" ? (
            <Card title="Invoices" aside="Wallet not connected">
              <Table
                columns={["Period", "Invoice", "Total in", "Total out", "Closing"]}
                empty="No invoices yet."
                rows={[]}
              />
            </Card>
          ) : null}
        </div>
      ) : null}

      {tab === "users" ? (
        <div className="flex flex-col gap-4">
          {canWrite ? (
            <form
              className="grid gap-3 rounded-2xl bg-white p-5 shadow-[0_0_0_1px_rgba(0,0,0,0.04)] md:grid-cols-[1fr_1fr_180px_auto]"
              onSubmit={inviteUser}
            >
              <label className="flex flex-col gap-1.5 text-sm">
                <span className="text-[#6E6E73]">Name</span>
                <input className={field} value={invite.full_name} required onChange={(event) => setInvite((current) => ({ ...current, full_name: event.target.value }))} />
              </label>
              <label className="flex flex-col gap-1.5 text-sm">
                <span className="text-[#6E6E73]">Email</span>
                <input className={field} type="email" value={invite.email} required onChange={(event) => setInvite((current) => ({ ...current, email: event.target.value }))} />
              </label>
              <label className="flex flex-col gap-1.5 text-sm">
                <span className="text-[#6E6E73]">Role</span>
                <select className={field} value={invite.role_name} onChange={(event) => setInvite((current) => ({ ...current, role_name: event.target.value }))}>
                  {ROLES.map((role) => (
                    <option key={role} value={role}>
                      {role}
                    </option>
                  ))}
                </select>
              </label>
              <div className="flex items-end">
                <button type="submit" className="h-10 rounded-full bg-[#1D1D1F] px-4 text-sm font-medium text-white">
                  Invite
                </button>
              </div>
              {token ? (
                <p className="text-sm md:col-span-4">
                  Invite token, shown once: <span className="break-all font-medium">{token}</span>
                </p>
              ) : null}
            </form>
          ) : null}
          <Card title="Users">
            <Table
              columns={["Name", "Email", "Roles", "Status"]}
              empty="No people on this account."
              rows={users.map((user) => [
                user.full_name,
                user.email,
                user.roles.join(", ") || "—",
                user.disabled ? "Disabled" : "Active",
              ])}
            />
          </Card>
        </div>
      ) : null}
    </div>
  );
}

function StatusPill({ status }: { status: string }) {
  const live = status === "active";
  return (
    <span
      className="inline-flex rounded-full px-2 py-0.5 text-xs font-medium capitalize"
      style={{
        color: live ? "#248A3D" : "#D70015",
        background: live ? "#E8F6EC" : "#FDECEC",
      }}
    >
      {status}
    </span>
  );
}

function Card({ title, aside, children }: { title: string; aside?: string; children: ReactNode }) {
  return (
    <section className="rounded-2xl bg-white px-5 pt-5 pb-4 shadow-[0_0_0_1px_rgba(0,0,0,0.04)]">
      <div className="mb-4 flex items-baseline justify-between gap-3">
        <h2 className="text-[17px] font-semibold tracking-[-0.2px]">{title}</h2>
        {aside ? <span className="text-[13px] text-[#86868B]">{aside}</span> : null}
      </div>
      {children}
    </section>
  );
}

function Table({ columns, rows, empty }: { columns: string[]; rows: string[][]; empty: string }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[640px] border-collapse text-left text-sm">
        <thead>
          <tr className="text-xs font-normal text-[#86868B]">
            {columns.map((column) => (
              <th key={column} className="py-2 pr-4 font-normal">
                {column}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.length === 0 ? (
            <tr>
              <td colSpan={columns.length} className="border-t border-[#F0F0F2] py-6 text-[#6E6E73]">
                {empty}
              </td>
            </tr>
          ) : (
            rows.map((row, index) => (
              <tr key={`${row[0]}-${index}`} className="hover:bg-[#FAFAFA]">
                {row.map((cell, cellIndex) => (
                  <td key={cellIndex} className="border-t border-[#F0F0F2] py-3 pr-4 text-[#1D1D1F]">
                    {cell}
                  </td>
                ))}
              </tr>
            ))
          )}
        </tbody>
      </table>
    </div>
  );
}
