// Frames for WS /admin/live-calls (VORA2-52).
// Connect sends a snapshot, then call.created / call.ringing / call.answered / call.ended.
// call.ended removes the row. Tests feed these frames from live-calls-fixture.ts.

export type CallDirection = "inbound" | "outbound";

export type LiveCall = {
  call_id: string;
  tenant_id?: string;
  tenant: string;
  agent: string;
  direction: CallDirection;
  number: string;
  started_at: string;
  state: "created" | "ringing" | "answered";
};

type ParsedCall = Omit<LiveCall, "state"> & {
  state: LiveCall["state"] | "ended";
};

export type LiveFrame =
  | { type: "snapshot"; calls: LiveCall[] }
  | { type: "call.created" | "call.ringing" | "call.answered"; call: LiveCall }
  | { type: "call.ended"; call_id: string };

export type LiveConnectionStatus = "connecting" | "live" | "reconnecting" | "unavailable";

export type LiveSocket = {
  onopen: (() => void) | null;
  onmessage: ((event: { data: string }) => void) | null;
  onclose: ((event: { code: number }) => void) | null;
  onerror: (() => void) | null;
  close: () => void;
};

const ACTIVE_STATES = new Set(["created", "ringing", "answered"]);
const DIRECTIONS = new Set<CallDirection>(["inbound", "outbound"]);
const DELTAS = new Set(["call.created", "call.ringing", "call.answered", "call.ended"]);
const REFUSED_CODES = new Set([1008, 4001, 4003, 4401, 4403]);
const RECONNECT_DELAYS_MS = [500, 1000, 2000, 4000, 8000, 15000];

function text(value: unknown): string | undefined {
  if (typeof value !== "string") return undefined;
  const trimmed = value.trim();
  return trimmed ? trimmed : undefined;
}

function label(value: unknown): string | undefined {
  const direct = text(value);
  if (direct) return direct;
  if (!value || typeof value !== "object") return undefined;
  const row = value as Record<string, unknown>;
  return text(row.name) ?? text(row.label);
}

function readCall(value: unknown): ParsedCall | null {
  if (!value || typeof value !== "object") return null;
  const row = value as Record<string, unknown>;
  const call_id = text(row.call_id);
  const tenantLabel = label(row.tenant);
  const tenant_id =
    text(row.tenant_id) ??
    (row.tenant && typeof row.tenant === "object" ? text((row.tenant as Record<string, unknown>).id) : undefined);
  const tenant = tenantLabel ?? tenant_id;
  const agent = label(row.agent);
  const direction = text(row.direction)?.toLowerCase();
  const number = text(row.number);
  const started_at = text(row.started_at);
  const state = text(row.state)?.toLowerCase();
  if (!call_id || !tenant || !agent || !direction || !number || !started_at || !state) return null;
  if (!DIRECTIONS.has(direction as CallDirection)) return null;
  if (state !== "ended" && !ACTIVE_STATES.has(state)) return null;
  return {
    call_id,
    tenant_id,
    tenant,
    agent,
    direction: direction as CallDirection,
    number,
    started_at,
    state: state as ParsedCall["state"],
  };
}

function activeCall(call: ParsedCall): LiveCall | null {
  if (call.state === "ended") return null;
  return {
    call_id: call.call_id,
    tenant_id: call.tenant_id,
    tenant: call.tenant,
    agent: call.agent,
    direction: call.direction,
    number: call.number,
    started_at: call.started_at,
    state: call.state,
  };
}

function withoutEnded(calls: LiveCall[]): LiveCall[] {
  const byId = new Map<string, LiveCall>();
  for (const call of calls) byId.set(call.call_id, call);
  return [...byId.values()];
}

export function parseLiveFrame(data: unknown): LiveFrame | null {
  let value = data;
  if (typeof data === "string") {
    try {
      value = JSON.parse(data) as unknown;
    } catch {
      return null;
    }
  }
  if (!value || typeof value !== "object") return null;
  const record = value as Record<string, unknown>;
  const name = text(record.type) ?? text(record.event);
  if (name === "snapshot") {
    if (!Array.isArray(record.calls)) return null;
    const calls: LiveCall[] = [];
    for (const item of record.calls) {
      const call = readCall(item);
      const active = call ? activeCall(call) : null;
      if (active) calls.push(active);
    }
    return { type: "snapshot", calls: withoutEnded(calls) };
  }
  if (!name || !DELTAS.has(name)) return null;
  if (name === "call.ended") {
    const nested = record.call && typeof record.call === "object" ? text((record.call as Record<string, unknown>).call_id) : undefined;
    const call_id = text(record.call_id) ?? nested;
    if (!call_id) return null;
    return { type: "call.ended", call_id };
  }
  const call = readCall(record.call) ?? readCall(record);
  if (!call) return null;
  const active = activeCall(call);
  if (!active) return { type: "call.ended", call_id: call.call_id };
  return { type: name as "call.created" | "call.ringing" | "call.answered", call: active };
}

export function applyLiveFrame(calls: LiveCall[], frame: LiveFrame): LiveCall[] {
  if (frame.type === "snapshot") return frame.calls.slice();
  if (frame.type === "call.ended") return calls.filter((call) => call.call_id !== frame.call_id);
  const index = calls.findIndex((call) => call.call_id === frame.call.call_id);
  if (index === -1) return [...calls, frame.call];
  const next = calls.slice();
  next[index] = frame.call;
  return next;
}

export function callTenantKey(call: LiveCall): string {
  return call.tenant_id || call.tenant;
}

export type TenantChoice = { key: string; label: string };

export function tenantChoices(calls: LiveCall[]): TenantChoice[] {
  const labels = new Map<string, string>();
  for (const call of calls) labels.set(callTenantKey(call), call.tenant);
  return [...labels.entries()]
    .map(([key, label]) => ({ key, label }))
    .sort((a, b) => a.label.localeCompare(b.label) || a.key.localeCompare(b.key));
}

export function rememberTenants(previous: TenantChoice[], calls: LiveCall[]): TenantChoice[] {
  const labels = new Map(previous.map((choice) => [choice.key, choice.label]));
  for (const choice of tenantChoices(calls)) labels.set(choice.key, choice.label);
  return [...labels.entries()]
    .map(([key, label]) => ({ key, label }))
    .sort((a, b) => a.label.localeCompare(b.label) || a.key.localeCompare(b.key));
}

export function filterCalls(calls: LiveCall[], tenantKey: string): LiveCall[] {
  if (!tenantKey) return calls;
  return calls.filter((call) => callTenantKey(call) === tenantKey);
}

export function sortLiveCalls(calls: LiveCall[]): LiveCall[] {
  return calls.slice().sort((a, b) => {
    const delta = Date.parse(b.started_at) - Date.parse(a.started_at);
    if (!Number.isNaN(delta) && delta !== 0) return delta;
    return a.call_id < b.call_id ? -1 : a.call_id > b.call_id ? 1 : 0;
  });
}

export function formatDuration(startedAt: string, nowMs: number): string {
  const start = Date.parse(startedAt);
  if (Number.isNaN(start)) return "—";
  const elapsed = Math.max(0, Math.floor((nowMs - start) / 1000));
  const hours = Math.floor(elapsed / 3600);
  const minutes = Math.floor((elapsed % 3600) / 60);
  const seconds = elapsed % 60;
  const ss = seconds.toString().padStart(2, "0");
  if (hours > 0) return `${hours}:${minutes.toString().padStart(2, "0")}:${ss}`;
  return `${minutes}:${ss}`;
}

export function reconnectDelayMs(attempt: number): number {
  const index = Math.min(RECONNECT_DELAYS_MS.length - 1, Math.max(0, Math.floor(attempt)));
  return RECONNECT_DELAYS_MS[index] ?? 15000;
}

export function liveCallsWebSocketUrl(apiBase: string, pageOrigin = ""): string {
  const trimmed = apiBase.trim();
  if (!trimmed) {
    const page = new URL(pageOrigin || "http://localhost:3000");
    const protocol = page.protocol === "https:" ? "wss:" : "ws:";
    return `${protocol}//${page.host}/api/admin/live-calls`;
  }
  const base = new URL(trimmed);
  const protocol = base.protocol === "https:" ? "wss:" : "ws:";
  const path = base.pathname.replace(/\/$/, "");
  const socketPath = path.endsWith("/api") ? `${path}/admin/live-calls` : "/admin/live-calls";
  return `${protocol}//${base.host}${socketPath}`;
}

function browserSocket(url: string): LiveSocket {
  const ws = new WebSocket(url);
  const socket: LiveSocket = {
    onopen: null,
    onmessage: null,
    onclose: null,
    onerror: null,
    close() {
      ws.close();
    },
  };
  ws.addEventListener("open", () => socket.onopen?.());
  ws.addEventListener("message", (event) => {
    if (typeof event.data === "string") socket.onmessage?.({ data: event.data });
  });
  ws.addEventListener("close", (event) => socket.onclose?.({ code: event.code }));
  ws.addEventListener("error", () => socket.onerror?.());
  return socket;
}

export function connectLiveCalls(options: {
  url: string;
  onFrame: (frame: LiveFrame) => void;
  onStatus: (status: LiveConnectionStatus) => void;
  openSocket?: (url: string) => LiveSocket;
  schedule?: (fn: () => void, ms: number) => { cancel: () => void };
  delay?: (attempt: number) => number;
}): () => void {
  const openSocket = options.openSocket ?? browserSocket;
  const schedule = options.schedule ?? ((fn, ms) => {
    const id = setTimeout(fn, ms);
    return { cancel: () => clearTimeout(id) };
  });
  const delay = options.delay ?? reconnectDelayMs;
  let stopped = false;
  let attempt = 0;
  let active: LiveSocket | null = null;
  let timer: { cancel: () => void } | null = null;

  const open = () => {
    if (stopped) return;
    options.onStatus(attempt === 0 ? "connecting" : "reconnecting");
    const current = openSocket(options.url);
    active = current;
    current.onopen = () => {
      if (stopped || active !== current) return;
      attempt = 0;
      options.onStatus("live");
    };
    current.onmessage = (event) => {
      if (stopped || active !== current) return;
      const frame = parseLiveFrame(event.data);
      if (frame) options.onFrame(frame);
    };
    current.onerror = () => undefined;
    current.onclose = (event) => {
      if (stopped || active !== current) return;
      active = null;
      if (REFUSED_CODES.has(event.code)) {
        options.onStatus("unavailable");
        return;
      }
      const wait = delay(attempt);
      attempt += 1;
      options.onStatus("reconnecting");
      timer = schedule(open, wait);
    };
  };

  open();

  return () => {
    stopped = true;
    timer?.cancel();
    active?.close();
    active = null;
  };
}
