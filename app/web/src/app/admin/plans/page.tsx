"use client";

import { useEffect, useState, type FormEvent } from "react";
import { Button } from "@/components/ui/button";

type Plan = {
  id: string;
  name: string;
  per_minute_rate_paise: number;
  transfer_leg_rate_paise: number;
  max_concurrent_calls: number;
  max_outbound_share_percent: number;
  max_agents: number;
  languages: string[];
  feature_flags: Record<string, boolean>;
};

const empty = {
  name: "",
  per_minute_rate_paise: "0",
  transfer_leg_rate_paise: "0",
  max_concurrent_calls: "1",
  max_outbound_share_percent: "100",
  max_agents: "1",
  languages: "hi,en",
  feature_flags: "",
};

export default function PlansPage() {
  const [plans, setPlans] = useState<Plan[]>([]);
  const [form, setForm] = useState(empty);
  const [editing, setEditing] = useState<string | null>(null);
  const [canWrite, setCanWrite] = useState(false);
  const [error, setError] = useState("");

  async function load() {
    const response = await fetch("/api/admin/plans", { credentials: "include" });
    if (!response.ok) return;
    const body = (await response.json()) as { plans: Plan[] };
    setPlans(body.plans);
  }

  useEffect(() => {
    let cancelled = false;
    async function run() {
      const [me, list] = await Promise.all([
        fetch("/api/auth/me", { credentials: "include" }).then((response) => response.json()),
        fetch("/api/admin/plans", { credentials: "include" }).then((response) => response.json()),
      ]);
      if (cancelled) return;
      setCanWrite(Boolean((me as { can_write?: boolean }).can_write));
      setPlans((list as { plans?: Plan[] }).plans ?? []);
    }
    void run();
    return () => {
      cancelled = true;
    };
  }, []);

  function setField(key: keyof typeof empty, value: string) {
    setForm((current) => ({ ...current, [key]: value }));
  }

  function payload() {
    let flags: Record<string, boolean> = {};
    if (form.feature_flags.trim()) {
      flags = JSON.parse(form.feature_flags) as Record<string, boolean>;
    }
    return {
      name: form.name,
      per_minute_rate_paise: Number(form.per_minute_rate_paise),
      transfer_leg_rate_paise: Number(form.transfer_leg_rate_paise),
      max_concurrent_calls: Number(form.max_concurrent_calls),
      max_outbound_share_percent: Number(form.max_outbound_share_percent),
      max_agents: Number(form.max_agents),
      languages: form.languages
        .split(",")
        .map((item) => item.trim())
        .filter(Boolean),
      feature_flags: flags,
    };
  }

  async function save(event: FormEvent) {
    event.preventDefault();
    setError("");
    let body: ReturnType<typeof payload>;
    try {
      body = payload();
    } catch {
      setError("Feature flags must be JSON");
      return;
    }
    const response = await fetch(editing ? `/api/admin/plans/${editing}` : "/api/admin/plans", {
      method: editing ? "PATCH" : "POST",
      headers: { "content-type": "application/json" },
      credentials: "include",
      body: JSON.stringify(body),
    });
    if (!response.ok) {
      const failure = (await response.json()) as { detail?: string };
      setError(failure.detail ?? "Could not save the plan");
      return;
    }
    setEditing(null);
    setForm(empty);
    await load();
  }

  return (
    <div className="flex flex-col gap-6">
      <header>
        <h1 className="text-2xl font-semibold">Plans & limits</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Rates are in paise. A tenant can override concurrency and rates.
        </p>
      </header>
      <div className="overflow-x-auto rounded-lg border border-border">
        <table className="w-full min-w-[720px] text-left text-sm">
          <thead className="bg-card text-muted-foreground">
            <tr>
              <th className="px-3 py-2 font-medium">Name</th>
              <th className="px-3 py-2 font-medium">Per minute</th>
              <th className="px-3 py-2 font-medium">Transfer</th>
              <th className="px-3 py-2 font-medium">Concurrent</th>
              <th className="px-3 py-2 font-medium">Outbound %</th>
              <th className="px-3 py-2 font-medium">Agents</th>
              <th className="px-3 py-2 font-medium">Languages</th>
            </tr>
          </thead>
          <tbody>
            {plans.map((plan) => (
              <tr key={plan.id} className="border-t border-border">
                <td className="px-3 py-2 font-medium">
                  {canWrite ? (
                    <button
                      type="button"
                      className="underline"
                      onClick={() => {
                        setEditing(plan.id);
                        setForm({
                          name: plan.name,
                          per_minute_rate_paise: String(plan.per_minute_rate_paise),
                          transfer_leg_rate_paise: String(plan.transfer_leg_rate_paise),
                          max_concurrent_calls: String(plan.max_concurrent_calls),
                          max_outbound_share_percent: String(plan.max_outbound_share_percent),
                          max_agents: String(plan.max_agents),
                          languages: plan.languages.join(","),
                          feature_flags: JSON.stringify(plan.feature_flags),
                        });
                      }}
                    >
                      {plan.name}
                    </button>
                  ) : (
                    plan.name
                  )}
                </td>
                <td className="px-3 py-2">{plan.per_minute_rate_paise}</td>
                <td className="px-3 py-2">{plan.transfer_leg_rate_paise}</td>
                <td className="px-3 py-2">{plan.max_concurrent_calls}</td>
                <td className="px-3 py-2">{plan.max_outbound_share_percent}</td>
                <td className="px-3 py-2">{plan.max_agents}</td>
                <td className="px-3 py-2">{plan.languages.join(", ")}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {canWrite ? (
        <form className="grid max-w-xl gap-3" onSubmit={save}>
          <h2 className="text-lg font-semibold">{editing ? "Edit plan" : "New plan"}</h2>
          {(
            [
              ["name", "Name"],
              ["per_minute_rate_paise", "Per-minute rate (paise)"],
              ["transfer_leg_rate_paise", "Transfer-leg rate (paise)"],
              ["max_concurrent_calls", "Max concurrent calls"],
              ["max_outbound_share_percent", "Max outbound share %"],
              ["max_agents", "Max agents"],
              ["languages", "Languages (comma separated)"],
              ["feature_flags", "Feature flags JSON"],
            ] as const
          ).map(([key, label]) => (
            <label key={key} className="flex flex-col gap-1 text-sm">
              {label}
              <input
                className="h-11 rounded-lg border border-border bg-card px-3"
                value={form[key]}
                onChange={(event) => setField(key, event.target.value)}
                required={key !== "feature_flags"}
              />
            </label>
          ))}
          <Button type="submit">{editing ? "Save plan" : "Create plan"}</Button>
        </form>
      ) : (
        <p className="text-sm text-muted-foreground">This role can view plans and cannot change them.</p>
      )}
      {error ? <p className="text-sm text-destructive">{error}</p> : null}
    </div>
  );
}
