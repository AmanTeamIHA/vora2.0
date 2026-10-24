"use client";

import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";

type Impersonation = {
  tenant_name: string;
  reason: string;
  actor_email: string;
};

export function ImpersonationBanner() {
  const [active, setActive] = useState<Impersonation | null>(null);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      const response = await fetch("/api/auth/me", { credentials: "include" });
      if (!response.ok) return;
      const body = (await response.json()) as { impersonation?: Impersonation };
      if (!cancelled) setActive(body.impersonation ?? null);
    }
    void load();
    return () => {
      cancelled = true;
    };
  }, []);

  if (!active) return null;

  async function stop() {
    await fetch("/api/admin/impersonate", { method: "DELETE", credentials: "include" });
    window.location.reload();
  }

  return (
    <div className="flex flex-wrap items-center justify-between gap-3 rounded-2xl bg-white px-5 py-3.5 text-sm shadow-[0_0_0_1px_rgba(0,0,0,0.04)]">
      <p className="flex items-center gap-3.5">
        <span className="size-2 shrink-0 rounded-full bg-[#FF3B30]" />
        <span>
          Impersonating <strong className="font-semibold">{active.tenant_name}</strong> as{" "}
          {active.actor_email}. Reason: {active.reason}. This session ends in 30 minutes.
        </span>
      </p>
      <Button type="button" variant="outline" onClick={() => void stop()}>
        Stop
      </Button>
    </div>
  );
}
