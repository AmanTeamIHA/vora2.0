"use client";

import { useEffect, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

const apiUrl = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

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
        const response = await fetch(`${apiUrl}/healthz`);
        const body = (await response.json()) as { status?: string };
        if (!cancelled) setHealth(response.ok ? (body.status ?? "down") : "down");
      } catch {
        if (!cancelled) setHealth("down");
      }

      try {
        const response = await fetch(`${apiUrl}/readyz`);
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

  return (
    <Card>
      <CardHeader>
        <CardTitle>Local stack</CardTitle>
        <CardDescription>API at {apiUrl}</CardDescription>
      </CardHeader>
      <CardContent className="flex flex-wrap gap-2">
        <Badge variant={health === "ok" ? "default" : "outline"}>API {health}</Badge>
        <Badge variant={ready?.postgres ? "default" : "outline"}>
          Postgres {ready ? (ready.postgres ? "ok" : "down") : "checking"}
        </Badge>
        <Badge variant={ready?.redis ? "default" : "outline"}>
          Redis {ready ? (ready.redis ? "ok" : "down") : "checking"}
        </Badge>
      </CardContent>
    </Card>
  );
}
