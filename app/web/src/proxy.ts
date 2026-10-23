import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";
import { adminNeedsLogin } from "@/lib/guard";

export function proxy(request: NextRequest) {
  const needsLogin = adminNeedsLogin(
    request.nextUrl.pathname,
    request.cookies.has("vora_access"),
  );
  if (needsLogin) {
    const url = request.nextUrl.clone();
    url.pathname = "/admin/login";
    return NextResponse.redirect(url);
  }
  return NextResponse.next();
}

export const config = {
  matcher: ["/admin/:path*"],
};
