"use client";

import { useEffect, useState } from "react";
import Link from "next/link";

type Tenant = {
  id: string;
  name: string;
  status: string;
  plan: string | null;
  calls_allowed: boolean;
};

type Counts = {
  tenants: number | null;
  numbers: number | null;
  users: number | null;
  outbound: string;
};

export function ControlBoard() {
  const [clock, setClock] = useState("");
  const [rows, setRows] = useState<Tenant[]>([]);
  const [counts, setCounts] = useState<Counts>({
    tenants: null,
    numbers: null,
    users: null,
    outbound: "—",
  });

  useEffect(() => {
    const tick = () =>
      setClock(
        new Date().toLocaleTimeString("en-IN", {
          timeZone: "Asia/Kolkata",
          hour: "numeric",
          minute: "2-digit",
          second: "2-digit",
          hour12: true,
        }),
      );
    tick();
    const id = setInterval(tick, 1000);
    return () => clearInterval(id);
  }, []);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      const [tenants, numbers, users, kill] = await Promise.all([
        fetch("/api/admin/tenants", { credentials: "include" }).then((response) => response.json()),
        fetch("/api/admin/numbers", { credentials: "include" }).then((response) => response.json()),
        fetch("/api/admin/users", { credentials: "include" }).then((response) => response.json()),
        fetch("/api/admin/kill-switch", { credentials: "include" }).then((response) => response.json()),
      ]);
      if (cancelled) return;
      const tenantRows = (tenants as { tenants?: Tenant[] }).tenants ?? [];
      setRows(tenantRows);
      const stopped = Boolean((kill as { global?: boolean }).global);
      setCounts({
        tenants: tenantRows.length,
        numbers: ((numbers as { numbers?: unknown[] }).numbers ?? []).length,
        users: ((users as { users?: unknown[] }).users ?? []).length,
        outbound: stopped ? "Stopped" : "On",
      });
    }
    void load();
    return () => {
      cancelled = true;
    };
  }, []);

  const cards = [
    { name: "Tenants", value: counts.tenants },
    { name: "Numbers", value: counts.numbers },
    { name: "Users", value: counts.users },
    { name: "Outbound", value: counts.outbound },
  ];

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-col gap-1.5">
        <h1 className="text-[32px] leading-none font-semibold tracking-[-0.8px]">Control board</h1>
        <p className="text-[15px] text-[#6E6E73]">
          Asia/Kolkata · <span className="tabular-nums">{clock}</span>
        </p>
      </div>

      <section aria-label="Key numbers" className="grid grid-cols-[repeat(auto-fit,minmax(210px,1fr))] gap-3.5">
        {cards.map((card) => (
          <div
            key={card.name}
            className="vora-card flex flex-col gap-1.5 rounded-2xl bg-white px-5 pt-5 pb-4 shadow-[0_0_0_1px_rgba(0,0,0,0.04)]"
          >
            <span className="text-[13px] text-[#6E6E73]">{card.name}</span>
            <span className="text-[30px] font-semibold tracking-[-0.6px] tabular-nums">
              {card.value ?? "—"}
            </span>
          </div>
        ))}
      </section>

      <section className="rounded-2xl bg-white px-[22px] pt-[22px] pb-3 shadow-[0_0_0_1px_rgba(0,0,0,0.04)]">
        <div className="mb-2 flex items-baseline">
          <h2 className="flex-1 text-[17px] font-semibold tracking-[-0.2px]">Tenants</h2>
          <Link href="/admin/tenants" className="text-[13px] text-[#6E6E73] no-underline">
            View all
          </Link>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[540px] border-collapse text-sm">
            <thead>
              <tr className="text-right text-xs font-normal text-[#86868B]">
                <th className="py-2.5 text-left font-normal">Name</th>
                <th className="py-2.5 font-normal">Plan</th>
                <th className="py-2.5 font-normal">Status</th>
                <th className="py-2.5 font-normal">Outbound</th>
              </tr>
            </thead>
            <tbody>
              {rows.length === 0 ? (
                <tr>
                  <td colSpan={4} className="border-t border-[#F0F0F2] py-3 text-[#6E6E73]">
                    No tenants yet.
                  </td>
                </tr>
              ) : (
                rows.map((tenant) => (
                  <tr key={tenant.id} className="text-right tabular-nums hover:bg-[#FAFAFA]">
                    <td className="border-t border-[#F0F0F2] py-3 text-left font-medium">
                      <Link href={`/admin/tenants/${tenant.id}`} className="text-[#1D1D1F] no-underline">
                        {tenant.name}
                      </Link>
                    </td>
                    <td className="border-t border-[#F0F0F2] py-3 text-[#424245]">{tenant.plan ?? "—"}</td>
                    <td
                      className="border-t border-[#F0F0F2] py-3"
                      style={{ color: tenant.status === "active" ? "#424245" : "#D70015" }}
                    >
                      {tenant.status}
                    </td>
                    <td className="border-t border-[#F0F0F2] py-3 text-[#424245]">
                      {tenant.calls_allowed ? "Allowed" : "Stopped"}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
