import { AccountChip } from "@/components/account-chip";
import { AskVora } from "@/components/ask-vora";
import { ShellHeader } from "@/components/shell-header";
import { SideNav } from "@/components/side-nav";
import { VoraMark } from "@/components/vora-mark";
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
    <div className="flex min-h-screen bg-[#F5F5F7] font-sans text-[#1D1D1F] antialiased">
      <aside className="flex w-full shrink-0 flex-col border-[#E8E8ED] bg-[#FBFBFD] px-3 py-[18px] md:w-[248px] md:border-r">
        <div className="flex items-center gap-2.5 px-2.5 pb-[22px] pt-1.5">
          <VoraMark />
          <span className="text-[19px] font-semibold tracking-[-0.4px]">vora</span>
          <span className="text-xs text-[#86868B]">{areaLabel}</span>
        </div>
        <SideNav items={items} />
        <AccountChip fallback={actor} />
      </aside>
      <div className="flex min-w-0 flex-1 flex-col">
        <ShellHeader />
        <main className="mx-auto flex w-full max-w-[1180px] flex-col gap-6 px-6 py-8 md:px-10 md:pt-11 md:pb-16">
          {children}
        </main>
      </div>
      <AskVora />
    </div>
  );
}
