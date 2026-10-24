export type Area = "admin" | "tenant";

export type NavItem = {
  label: string;
  href: string;
  ready: boolean;
  group?: string;
};

export const adminNav: NavItem[] = [
  { group: "Operations", label: "Control board", href: "/admin", ready: true },
  { group: "Operations", label: "Live calls", href: "/admin/live", ready: true },
  { group: "Operations", label: "Reports", href: "/admin/reports", ready: false },
  { group: "Customers", label: "Tenants", href: "/admin/tenants", ready: true },
  { group: "Customers", label: "Users & roles", href: "/admin/users", ready: true },
  { group: "Customers", label: "KYC reviews", href: "/admin/kyc", ready: false },
  { group: "Customers", label: "Resellers", href: "/admin/resellers", ready: false },
  { group: "Voice", label: "Agents", href: "/admin/agents", ready: false },
  { group: "Voice", label: "Numbers", href: "/admin/numbers", ready: true },
  { group: "Voice", label: "Trunk & capacity", href: "/admin/trunk", ready: false },
  { group: "Platform", label: "Plans & limits", href: "/admin/plans", ready: true },
  { group: "Platform", label: "Billing", href: "/admin/billing", ready: false },
  { group: "Platform", label: "Audit log", href: "/admin/audit", ready: true },
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
