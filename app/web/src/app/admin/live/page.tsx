"use client";

import { Suspense } from "react";
import { useSearchParams } from "next/navigation";
import { LiveCallsView } from "../../../../admin/live-calls-view";

function LiveCallsPage() {
  const fixture = useSearchParams().get("fixture") === "1";
  return <LiveCallsView fixture={fixture} />;
}

export default function LiveCallsRoute() {
  return (
    <Suspense fallback={<p className="text-sm text-[#6E6E73]">Loading…</p>}>
      <LiveCallsPage />
    </Suspense>
  );
}
