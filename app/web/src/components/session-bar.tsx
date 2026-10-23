"use client";

import { useEffect, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

type Me = { email: string; roles: string[]; can_write: boolean };

export function SessionBar() {
  const [me, setMe] = useState<Me | null>(null);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      const response = await fetch("/api/auth/me", { credentials: "include" });
      if (!response.ok) return;
      const body = (await response.json()) as Me;
      if (!cancelled) setMe(body);
    }
    void load();
    return () => {
      cancelled = true;
    };
  }, []);

  if (!me) return null;

  return (
    <Card>
      <CardHeader>
        <CardTitle>{me.email}</CardTitle>
      </CardHeader>
      <CardContent className="text-sm text-muted-foreground">
        {me.roles.join(", ") || "No role"} · {me.can_write ? "Can change data" : "Read only"}
      </CardContent>
    </Card>
  );
}
