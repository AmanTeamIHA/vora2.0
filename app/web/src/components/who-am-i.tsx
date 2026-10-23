"use client";

import { useEffect, useState } from "react";

export function WhoAmI() {
  const [label, setLabel] = useState("Signed out");

  useEffect(() => {
    let cancelled = false;
    async function load() {
      const response = await fetch("/api/auth/me", { credentials: "include" });
      if (!response.ok) return;
      const body = (await response.json()) as { email?: string };
      if (!cancelled && body.email) setLabel(body.email);
    }
    void load();
    return () => {
      cancelled = true;
    };
  }, []);

  return <>{label}</>;
}
