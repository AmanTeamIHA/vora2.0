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
    <div className="mb-4 flex flex-wrap items-center justify-between gap-3 rounded-lg bg-red-700 px-4 py-3 text-sm text-white">
      <p>
        Impersonating <strong>{active.tenant_name}</strong> as {active.actor_email}. Reason:{" "}
        {active.reason}. This session ends in 30 minutes.
      </p>
      <Button type="button" variant="outline" onClick={() => void stop()}>
        Stop
      </Button>
    </div>
  );
}
