"use client";

import { useEffect, useState } from "react";

type Ready = {
  status: string;
  postgres: boolean;
  redis: boolean;
};

export function StackStatus() {
  const [health, setHealth] = useState("checking");
  const [ready, setReady] = useState<Ready | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      try {
        const response = await fetch("/api/healthz");
        const body = (await response.json()) as { status?: string };
        if (!cancelled) setHealth(response.ok ? (body.status ?? "down") : "down");
      } catch {
        if (!cancelled) setHealth("down");
      }

      try {
        const response = await fetch("/api/readyz");
        const body = (await response.json()) as Ready;
        if (!cancelled) setReady(body);
      } catch {
        if (!cancelled) setReady({ status: "down", postgres: false, redis: false });
      }
    }

    void load();
    return () => {
      cancelled = true;
    };
  }, []);

  const dots = [
    { name: "API", ok: health === "ok" },
    { name: "Postgres", ok: Boolean(ready?.postgres) },
    { name: "Redis", ok: Boolean(ready?.redis) },
  ];

  return (
    <section className="rounded-2xl bg-white px-[22px] py-5 shadow-[0_0_0_1px_rgba(0,0,0,0.04)]">
      <h2 className="text-[17px] font-semibold tracking-[-0.2px]">System</h2>
      <div className="mt-3 flex flex-wrap gap-x-3.5 gap-y-2 text-[13px] text-[#424245]">
        {dots.map((item) => (
          <span key={item.name} className="flex items-center gap-1.5">
            <span
              className="size-1.5 rounded-full"
              style={{ background: item.ok ? "#34C759" : "#FF3B30" }}
            />
            {item.name}
            {item.ok ? "" : " down"}
          </span>
        ))}
      </div>
    </section>
  );
}
