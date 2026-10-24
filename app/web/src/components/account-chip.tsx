"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

type Me = { email?: string; roles?: string[] };

export function AccountChip({ fallback }: { fallback?: React.ReactNode }) {
  const router = useRouter();
  const [me, setMe] = useState<Me | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

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

  async function signOut() {
    setBusy(true);
    setError("");
    const response = await fetch("/api/auth/logout", { method: "POST", credentials: "include" });
    if (!response.ok && response.status !== 401) {
      setBusy(false);
      setError("Could not log out");
      return;
    }
    router.push("/admin/login");
    router.refresh();
  }

  const email = me?.email ?? "";
  const local = email.split("@")[0] ?? "";
  const name = local ? local.charAt(0).toUpperCase() + local.slice(1) : "";
  const role = me?.roles?.[0] ?? "";

  return (
    <div className="mt-auto flex flex-col border-t border-[#E8E8ED] px-3 pb-1 pt-3">
      <div className="flex items-center gap-2.5">
        <span className="flex size-[30px] items-center justify-center rounded-full bg-[#1D1D1F] text-[13px] font-semibold text-white">
          {name ? name.charAt(0) : "·"}
        </span>
        <span className="flex min-w-0 flex-1 flex-col">
          <span className="truncate text-[13px] font-medium text-[#1D1D1F]">
            {name || fallback || "Signed out"}
          </span>
          <span className="flex items-center gap-2">
            {role ? <span className="text-xs text-[#86868B]">{role}</span> : null}
            <button
              type="button"
              onClick={() => void signOut()}
              disabled={busy}
              className="text-xs text-[#1D1D1F] underline-offset-2 hover:underline disabled:opacity-50"
            >
              Log out
            </button>
          </span>
        </span>
        <span className="rounded-full border border-[#D2D2D7] px-2 py-0.5 text-[11px] text-[#6E6E73]">
          Dev
        </span>
      </div>
      {error ? <p className="pt-1 text-xs text-[#D70015]">{error}</p> : null}
    </div>
  );
}
