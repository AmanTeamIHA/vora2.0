"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "cn";
import { navIsActive, type NavItem } from "@/lib/nav";

const iconProps = {
  width: 17,
  height: 17,
  viewBox: "0 0 24 24",
  fill: "none",
  stroke: "currentColor",
  strokeWidth: 1.8,
  strokeLinecap: "round" as const,
  "aria-hidden": true,
};

function Icon({ label }: { label: string }) {
  switch (label) {
    case "Control board":
      return (
        <svg {...iconProps}>
          <rect x="3" y="3" width="7" height="7" rx="2" />
          <rect x="14" y="3" width="7" height="7" rx="2" />
          <rect x="3" y="14" width="7" height="7" rx="2" />
          <rect x="14" y="14" width="7" height="7" rx="2" />
        </svg>
      );
    case "Live calls":
      return (
        <svg {...iconProps}>
          <path d="M5 4h4l2 5-2.5 1.5a11 11 0 0 0 5 5L15 13l5 2v4a2 2 0 0 1-2 2A16 16 0 0 1 3 6a2 2 0 0 1 2-2" />
        </svg>
      );
    case "Reports":
      return (
        <svg {...iconProps}>
          <path d="M4 20V4M9 20v-8M14 20V9M19 20v-5" />
        </svg>
      );
    case "Tenants":
      return (
        <svg {...iconProps}>
          <rect x="4" y="3" width="16" height="18" rx="2" />
          <path d="M9 7h1M14 7h1M9 11h1M14 11h1M10 21v-4h4v4" />
        </svg>
      );
    case "Users & roles":
      return (
        <svg {...iconProps}>
          <circle cx="12" cy="8" r="4" />
          <path d="M4 21a8 8 0 0 1 16 0" />
        </svg>
      );
    case "KYC reviews":
      return (
        <svg {...iconProps}>
          <path d="M12 3l8 3v6c0 4.5-3.4 8-8 9-4.6-1-8-4.5-8-9V6z" />
        </svg>
      );
    case "Resellers":
      return (
        <svg {...iconProps}>
          <circle cx="9" cy="8" r="3.5" />
          <path d="M2.5 20a6.5 6.5 0 0 1 13 0M18 8v6M15 11h6" />
        </svg>
      );
    case "Agents":
      return (
        <svg {...iconProps}>
          <rect x="4" y="4" width="16" height="16" rx="5" />
          <path d="M9 9v2M15 9v2M9.5 15h5" />
        </svg>
      );
    case "Numbers":
      return (
        <svg {...iconProps}>
          <path d="M5 9h14M5 15h14M10 3L8 21M16 3l-2 18" />
        </svg>
      );
    case "Trunk & capacity":
      return (
        <svg {...iconProps}>
          <path d="M3 12h4l3-8 4 16 3-8h4" />
        </svg>
      );
    case "Plans & limits":
      return (
        <svg {...iconProps}>
          <path d="M20 12l-8 8-9-9V3h8z" />
          <circle cx="7.5" cy="7.5" r="1.5" />
        </svg>
      );
    case "Billing":
      return (
        <svg {...iconProps}>
          <rect x="3" y="6" width="18" height="13" rx="2.5" />
          <path d="M3 10h18" />
        </svg>
      );
    case "Audit log":
      return (
        <svg {...iconProps}>
          <path d="M6 3h9l4 4v14H6z" />
          <path d="M9 12h7M9 16h7" />
        </svg>
      );
    default:
      return null;
  }
}

export function SideNav({ items }: { items: NavItem[] }) {
  const pathname = usePathname();
  const groups: string[] = [];
  for (const item of items) {
    const group = item.group ?? "";
    if (!groups.includes(group)) groups.push(group);
  }

  return (
    <nav aria-label="Vora admin" className="flex flex-col">
      {groups.map((group) => (
        <div key={group || "nav"} className="flex flex-col">
          {group ? (
            <span className="px-3 pb-1.5 pt-[18px] text-xs text-[#86868B] first:pt-1">{group}</span>
          ) : null}
          {items
            .filter((item) => (item.group ?? "") === group)
            .map((item) => {
              const active = item.ready && navIsActive(pathname, item.href, items);
              if (!item.ready) {
                return (
                  <span
                    key={item.href}
                    className="flex items-center gap-[11px] rounded-[9px] px-3 py-[9px] text-sm text-[#86868B]"
                  >
                    <Icon label={item.label} />
                    <span className="truncate">{item.label}</span>
                    <span className="ml-auto rounded-full bg-[#EBEBED] px-[7px] py-px text-[11px] text-[#86868B]">
                      Soon
                    </span>
                  </span>
                );
              }
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  className={cn(
                    "vora-nav flex items-center gap-[11px] rounded-[9px] px-3 py-[9px] text-sm no-underline",
                    active
                      ? "bg-white font-medium text-[#1D1D1F] shadow-[0_1px_2px_rgba(0,0,0,0.06),0_0_0_1px_rgba(0,0,0,0.04)]"
                      : "text-[#424245]",
                  )}
                >
                  <Icon label={item.label} />
                  {item.label}
                </Link>
              );
            })}
        </div>
      ))}
    </nav>
  );
}
