"use client";

import { useEffect, useState, type FormEvent } from "react";
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

const fieldClass =
  "h-10 w-full rounded-lg border border-[#E8E8ED] bg-white px-3 text-sm text-[#1D1D1F] outline-none focus:border-[#1D1D1F]";

export default function TenantsPage() {
  const router = useRouter();
  const params = useSearchParams();
  const query = params.get("q") ?? "";
  const status = params.get("status") ?? "";
  const plan = params.get("plan") ?? "";
  const [draft, setDraft] = useState(query);
  const [seenQuery, setSeenQuery] = useState(query);
  if (query !== seenQuery) {
    setSeenQuery(query);
    setDraft(query);
  }
  const [revision, setRevision] = useState(0);
  const [tenants, setTenants] = useState<Tenant[]>([]);
  const [plans, setPlans] = useState<string[]>(["Starter"]);
  const [form, setForm] = useState(emptyForm);
  const [creating, setCreating] = useState(false);
  const [canWrite, setCanWrite] = useState(false);
  const [invite, setInvite] = useState<(Invite & { id: string; name: string }) | null>(null);
  const [error, setError] = useState("");
  const [loaded, setLoaded] = useState(false);

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
      const search = new URLSearchParams();
      if (query) search.set("q", query);
      if (status) search.set("status", status);
      if (plan) search.set("plan", plan);
      const response = await fetch(`/api/admin/tenants?${search}`, { credentials: "include" });
      if (cancelled) return;
      if (!response.ok) {
        setError("Could not load tenants");
        setLoaded(true);
        return;
      }
      const body = (await response.json()) as { tenants: Tenant[] };
      setTenants(body.tenants);
      setLoaded(true);
    }
    void run();
    return () => {
      cancelled = true;
    };
  }, [query, status, plan, revision]);

  function replace(next: { q?: string; status?: string; plan?: string }) {
    const search = new URLSearchParams(params.toString());
    const values = { q: query, status, plan, ...next };
    for (const [key, value] of Object.entries(values)) {
      if (value) search.set(key, value);
      else search.delete(key);
    }
    const suffix = search.toString();
    router.replace(suffix ? `/admin/tenants?${suffix}` : "/admin/tenants");
  }

  async function create(event: FormEvent) {
    event.preventDefault();
    setError("");
    const response = await fetch("/api/admin/tenants", {
      method: "POST",
      headers: { "content-type": "application/json" },
      credentials: "include",
      body: JSON.stringify(form),
    });
    const body = (await response.json()) as {
      id?: string;
      name?: string;
      detail?: string;
      invite?: Invite;
    };
    if (!response.ok || !body.id) {
      setError(typeof body.detail === "string" ? body.detail : "Could not create the tenant");
      return;
    }
    setForm(emptyForm);
    setCreating(false);
    if (body.invite) setInvite({ ...body.invite, id: body.id, name: body.name ?? form.name });
    setRevision((current) => current + 1);
  }

  return (
    <div className="flex flex-col gap-5">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-[32px] leading-none font-semibold tracking-[-0.8px]">Tenants</h1>
          <p className="mt-2 text-[15px] text-[#6E6E73]">
            Open an account to work its calls, agents, numbers, billing, and people.
          </p>
        </div>
        {canWrite ? (
          <button
            type="button"
            className="h-10 rounded-full bg-[#1D1D1F] px-4 text-sm font-medium text-white"
            onClick={() => setCreating((open) => !open)}
          >
            {creating ? "Close" : "New tenant"}
          </button>
        ) : null}
      </header>

      {invite ? (
        <div className="rounded-2xl bg-white px-5 py-4 text-sm shadow-[0_0_0_1px_rgba(0,0,0,0.04)]">
          <p>
            {invite.name} is ready. Tenant Admin invite for {invite.email}. Token, shown once:{" "}
            <span className="break-all font-medium">{invite.token}</span>
          </p>
          <Link href={`/admin/tenants/${invite.id}`} className="mt-2 inline-block text-[#1D1D1F]">
            Open the account
          </Link>
        </div>
      ) : null}

      {creating ? (
        <form
          className="grid gap-4 rounded-2xl bg-white p-5 shadow-[0_0_0_1px_rgba(0,0,0,0.04)] md:grid-cols-2"
          onSubmit={create}
        >
          <h2 className="text-[17px] font-semibold md:col-span-2">New tenant</h2>
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
            <label key={key} className="flex flex-col gap-1.5 text-sm">
              <span className="text-[#6E6E73]">{label}</span>
              <input
                className={fieldClass}
                value={form[key]}
                onChange={(event) => setForm((current) => ({ ...current, [key]: event.target.value }))}
                required={key !== "gstin" && key !== "contact_phone"}
              />
            </label>
          ))}
          <label className="flex flex-col gap-1.5 text-sm">
            <span className="text-[#6E6E73]">Plan</span>
            <select
              className={fieldClass}
              value={form.plan_name}
              onChange={(event) => setForm((current) => ({ ...current, plan_name: event.target.value }))}
            >
              {plans.map((name) => (
                <option key={name} value={name}>
                  {name}
                </option>
              ))}
            </select>
          </label>
          <div className="flex items-end">
            <button type="submit" className="h-10 rounded-full bg-[#1D1D1F] px-4 text-sm font-medium text-white">
              Create tenant
            </button>
          </div>
        </form>
      ) : null}

      <form
        className="flex flex-wrap gap-2"
        onSubmit={(event) => {
          event.preventDefault();
          replace({ q: draft });
        }}
      >
        <input
          className="h-10 min-w-[240px] flex-1 rounded-full border border-[#E8E8ED] bg-white px-4 text-sm outline-none focus:border-[#1D1D1F]"
          placeholder="Search name, legal entity, GSTIN"
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          aria-label="Search tenants"
        />
        <select
          className="h-10 rounded-full border border-[#E8E8ED] bg-white px-3 text-sm"
          value={status}
          onChange={(event) => replace({ status: event.target.value })}
          aria-label="Status"
        >
          <option value="">Any status</option>
          <option value="active">Active</option>
          <option value="suspended">Suspended</option>
        </select>
        <select
          className="h-10 rounded-full border border-[#E8E8ED] bg-white px-3 text-sm"
          value={plan}
          onChange={(event) => replace({ plan: event.target.value })}
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

      <div className="overflow-x-auto rounded-2xl bg-white shadow-[0_0_0_1px_rgba(0,0,0,0.04)]">
        <table className="w-full min-w-[720px] border-collapse text-left text-sm">
          <thead className="text-xs font-normal text-[#86868B]">
            <tr>
              <th className="px-4 py-3 font-normal">Name</th>
              <th className="px-4 py-3 font-normal">Plan</th>
              <th className="px-4 py-3 font-normal">Status</th>
              <th className="px-4 py-3 font-normal">Outbound</th>
              <th className="px-4 py-3 font-normal">Contact</th>
            </tr>
          </thead>
          <tbody>
            {tenants.length === 0 ? (
              <tr>
                <td colSpan={5} className="border-t border-[#F0F0F2] px-4 py-8 text-[#6E6E73]">
                  {loaded ? "No tenants match." : "Loading accounts…"}
                </td>
              </tr>
            ) : (
              tenants.map((tenant) => (
                <tr key={tenant.id} className="hover:bg-[#FAFAFA]">
                  <td className="border-t border-[#F0F0F2] px-4 py-3.5">
                    <Link href={`/admin/tenants/${tenant.id}`} className="text-[#1D1D1F] no-underline">
                      <span className="block font-medium">{tenant.name}</span>
                      <span className="text-[13px] text-[#6E6E73]">{tenant.legal_name}</span>
                    </Link>
                  </td>
                  <td className="border-t border-[#F0F0F2] px-4 py-3.5 text-[#424245]">
                    {tenant.plan ?? "—"}
                  </td>
                  <td className="border-t border-[#F0F0F2] px-4 py-3.5">
                    <StatusPill status={tenant.status} />
                  </td>
                  <td className="border-t border-[#F0F0F2] px-4 py-3.5 text-[#424245]">
                    {tenant.calls_allowed ? "Allowed" : "Stopped"}
                  </td>
                  <td className="border-t border-[#F0F0F2] px-4 py-3.5 text-[#424245]">
                    {tenant.contact_email}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
      {error ? <p className="text-sm text-[#D70015]">{error}</p> : null}
    </div>
  );
}

function StatusPill({ status }: { status: string }) {
  const live = status === "active";
  return (
    <span
      className="inline-flex rounded-full px-2 py-0.5 text-xs font-medium"
      style={{
        color: live ? "#248A3D" : "#D70015",
        background: live ? "#E8F6EC" : "#FDECEC",
      }}
    >
      {status}
    </span>
  );
}
