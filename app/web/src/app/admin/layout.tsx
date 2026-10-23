import { Suspense } from "react";
import { AppShell } from "@/components/app-shell";
import { ImpersonationBanner } from "@/components/impersonation-banner";
import { WhoAmI } from "@/components/who-am-i";
import { adminNav } from "@/lib/nav";

export default function AdminLayout({ children }: LayoutProps<"/admin">) {
  return (
    <AppShell areaLabel="Super Admin" actor={<WhoAmI />} items={adminNav}>
      <ImpersonationBanner />
      <Suspense fallback={<p className="text-sm text-muted-foreground">Loading…</p>}>{children}</Suspense>
    </AppShell>
  );
}
