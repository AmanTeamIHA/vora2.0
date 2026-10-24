"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

type AgentRow = {
  id: string;
  name: string;
  tenant_name: string;
  greeting: string;
};

export default function AgentsPage() {
  const [agents, setAgents] = useState<AgentRow[]>([]);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    async function load() {
      const response = await fetch("/api/admin/agents", { credentials: "include" });
      const body = (await response.json().catch(() => ({}))) as {
        agents?: AgentRow[];
        detail?: string;
      };
      if (cancelled) return;
      if (!response.ok) {
        setError(typeof body.detail === "string" ? body.detail : "Could not load agents");
        return;
      }
      setAgents(body.agents ?? []);
    }
    void load();
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <div className="flex flex-col gap-6">
      <header>
        <h1 className="text-[32px] leading-none font-semibold tracking-[-0.8px]">Agents</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Deployed agents. Open one to talk to it in the browser.
        </p>
      </header>
      {error ? <p className="text-sm text-[#D70015]">{error}</p> : null}
      <div className="overflow-x-auto rounded-2xl bg-white shadow-[0_0_0_1px_rgba(0,0,0,0.04)]">
        <table className="w-full min-w-[640px] text-left text-sm">
          <thead className="text-xs text-[#86868B]">
            <tr>
              <th className="px-3 py-2 font-medium">Agent</th>
              <th className="px-3 py-2 font-medium">Tenant</th>
              <th className="px-3 py-2 font-medium">Greeting</th>
            </tr>
          </thead>
          <tbody>
            {agents.map((agent) => (
              <tr key={agent.id} className="border-t border-border">
                <td className="px-3 py-3">
                  <Link
                    href={`/admin/agents/${agent.id}/test`}
                    className="font-medium text-[#1D1D1F] no-underline"
                  >
                    {agent.name}
                  </Link>
                </td>
                <td className="px-3 py-3 text-[#424245]">{agent.tenant_name}</td>
                <td className="px-3 py-3 text-[#6E6E73]">{agent.greeting || "—"}</td>
              </tr>
            ))}
            {agents.length === 0 && !error ? (
              <tr>
                <td className="px-3 py-6 text-[#6E6E73]" colSpan={3}>
                  No agents yet.
                </td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </div>
    </div>
  );
}
