import { Suspense } from "react";
import { TenantProfile } from "@/components/tenant-profile";

export default function TenantProfilePage({ params }: PageProps<"/admin/tenants/[id]">) {
  return (
    <Suspense fallback={<p className="text-sm text-[#6E6E73]">Loading account…</p>}>
      {params.then(({ id }) => (
        <TenantProfile id={id} />
      ))}
    </Suspense>
  );
}
