import { NextResponse } from "next/server";

async function proxy(request: Request, context: { params: Promise<{ path: string[] }> }) {
  const { path } = await context.params;
  const base = process.env.API_INTERNAL_URL ?? "http://127.0.0.1:8000";
  const target = new URL(`${base}/${path.join("/")}`);
  const incoming = new URL(request.url);
  target.search = incoming.search;

  const headers = new Headers(request.headers);
  headers.delete("host");
  const init: RequestInit = { method: request.method, headers, redirect: "manual" };
  if (request.method !== "GET" && request.method !== "HEAD") {
    init.body = await request.arrayBuffer();
  }

  const response = await fetch(target, init);
  const outHeaders = new Headers();
  response.headers.forEach((value, key) => {
    if (key.toLowerCase() !== "set-cookie") outHeaders.append(key, value);
  });
  for (const cookie of response.headers.getSetCookie()) {
    outHeaders.append("set-cookie", cookie);
  }
  return new NextResponse(response.body, { status: response.status, headers: outHeaders });
}

export const GET = proxy;
export const POST = proxy;
export const PATCH = proxy;
