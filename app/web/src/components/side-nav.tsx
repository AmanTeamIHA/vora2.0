"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "cn";
import type { NavItem } from "@/lib/nav";

export function SideNav({ items }: { items: NavItem[] }) {
  const pathname = usePathname();

  return (
    <nav aria-label="Sections" className="flex gap-1 overflow-x-auto md:flex-col">
      {items.map((item) => {
        const active = item.ready && (pathname === item.href || pathname.startsWith(`${item.href}/`));
        if (!item.ready) {
          return (
            <span
              key={item.href}
              className="shrink-0 whitespace-nowrap rounded-lg px-3 py-2.5 text-sm text-sidebar-foreground/45"
              title="Not built yet"
            >
              {item.label}
            </span>
          );
        }
        return (
          <Link
            key={item.href}
            href={item.href}
            className={cn(
              "shrink-0 whitespace-nowrap rounded-lg px-3 py-2.5 text-sm",
              active
                ? "bg-sidebar-accent font-medium text-sidebar-accent-foreground"
                : "text-sidebar-foreground hover:bg-sidebar-accent/70",
            )}
          >
            {item.label}
          </Link>
        );
      })}
    </nav>
  );
}
