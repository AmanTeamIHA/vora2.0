import { Suspense } from "react";
import { StackStatus } from "@/components/stack-status";

export default function TenantHome({ params }: PageProps<"/t/[tenant]">) {
  return (
    <Suspense fallback={<p className="text-sm text-muted-foreground">Loading workspace…</p>}>
      {params.then(({ tenant }) => (
        <div className="flex flex-col gap-6">
          <header>
            <h1 className="text-2xl font-semibold">{tenant}</h1>
            <p className="mt-1 text-sm text-muted-foreground">
              Tenant workspace. This shell only links inside /t/{tenant}.
            </p>
          </header>
          <StackStatus />
        </div>
      ))}
    </Suspense>
  );
}
