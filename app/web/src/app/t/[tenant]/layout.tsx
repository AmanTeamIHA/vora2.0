import { Suspense } from "react";
import { AppShell } from "@/components/app-shell";
import { tenantNav } from "@/lib/nav";

export default function TenantLayout({ children, params }: LayoutProps<"/t/[tenant]">) {
  return (
    <Suspense fallback={<p className="p-8 text-sm text-muted-foreground">Loading workspace…</p>}>
      {params.then(({ tenant }) => (
        <AppShell areaLabel="Tenant" actor={tenant} items={tenantNav(tenant)}>
          {children}
        </AppShell>
      ))}
    </Suspense>
  );
}
