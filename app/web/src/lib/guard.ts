export function adminNeedsLogin(pathname: string, hasAccessCookie: boolean): boolean {
  if (!pathname.startsWith("/admin")) return false;
  if (pathname === "/admin/login") return false;
  return !hasAccessCookie;
}
