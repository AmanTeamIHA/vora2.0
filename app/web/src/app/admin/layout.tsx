import { Suspense } from "react";
import { AppShell } from "@/components/app-shell";
import { ImpersonationBanner } from "@/components/impersonation-banner";
import { adminNav } from "@/lib/nav";

export default function AdminLayout({ children }: LayoutProps<"/admin">) {
  return (
    <AppShell areaLabel="Admin" actor="Signed out" items={adminNav}>
      <ImpersonationBanner />
      <Suspense fallback={<p className="text-sm text-muted-foreground">Loading…</p>}>{children}</Suspense>
    </AppShell>
  );
}
