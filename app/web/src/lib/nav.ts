export type Area = "admin" | "tenant";

export type NavItem = {
  label: string;
  href: string;
  ready: boolean;
};

export const adminNav: NavItem[] = [
  { label: "Overview", href: "/admin", ready: true },
  { label: "Live calls", href: "/admin/live", ready: false },
  { label: "Tenants", href: "/admin/tenants", ready: true },
  { label: "Plans & limits", href: "/admin/plans", ready: false },
  { label: "Numbers", href: "/admin/numbers", ready: false },
  { label: "Users & roles", href: "/admin/users", ready: false },
  { label: "Audit log", href: "/admin/audit", ready: false },
];

export function navIsActive(pathname: string, href: string, items: NavItem[]): boolean {
  const matches = (value: string) => pathname === value || pathname.startsWith(`${value}/`);
  if (!matches(href)) return false;
  return !items.some(
    (other) => other.href !== href && other.href.startsWith(`${href}/`) && matches(other.href),
  );
}

export function tenantNav(tenant: string): NavItem[] {
  const base = `/t/${tenant}`;
  return [
    { label: "Home", href: base, ready: true },
    { label: "Calls", href: `${base}/calls`, ready: false },
    { label: "Team", href: `${base}/team`, ready: false },
  ];
}
