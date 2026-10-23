import { SideNav } from "@/components/side-nav";
import type { NavItem } from "@/lib/nav";

export function AppShell({
  areaLabel,
  actor,
  items,
  children,
}: {
  areaLabel: string;
  actor: React.ReactNode;
  items: NavItem[];
  children: React.ReactNode;
}) {
  return (
    <div className="flex min-h-screen flex-col bg-background text-foreground md:flex-row">
      <aside className="flex w-full shrink-0 flex-col gap-3 bg-sidebar px-3.5 py-4 text-sidebar-foreground md:w-60 md:py-5">
        <div className="flex items-center gap-2.5 px-2.5">
          <div className="flex size-8 items-center justify-center rounded-lg bg-sidebar-primary text-sm font-semibold text-sidebar-primary-foreground">
            V
          </div>
          <div className="flex min-w-0 flex-1 flex-col">
            <span className="text-[15px] font-semibold text-white">Vora 2.0</span>
            <span className="text-xs text-[#9aa6b6]">{areaLabel}</span>
          </div>
          <p className="truncate text-[13px] text-white md:hidden">{actor}</p>
        </div>
        <SideNav items={items} />
        <div className="mt-auto hidden rounded-lg bg-[#16233a] px-3 py-3 md:block">
          <p className="font-mono text-xs text-[#fde68a]">DEV · ap-south-1</p>
          <p className="mt-1 text-[13px] text-white">{actor}</p>
        </div>
      </aside>
      <main className="min-w-0 flex-1 px-4 py-6 md:px-8 md:py-7">{children}</main>
    </div>
  );
}
