import { Suspense } from "react";
import { AppShell } from "@/components/app-shell";
import { adminNav } from "@/lib/nav";

export default function AdminLayout({ children }: LayoutProps<"/admin">) {
  return (
    <AppShell areaLabel="Super Admin" actor="Signed out" items={adminNav}>
      <Suspense fallback={<p className="text-sm text-muted-foreground">Loading…</p>}>{children}</Suspense>
    </AppShell>
  );
}
