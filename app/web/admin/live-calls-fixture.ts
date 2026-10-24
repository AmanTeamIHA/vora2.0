import type { LiveCall, LiveFrame } from "./live-calls.ts";

const aarohi: LiveCall = {
  call_id: "call_aarohi_1",
  tenant_id: "ten_aarohi",
  tenant: "Aarohi Clinics",
  agent: "Reception",
  direction: "inbound",
  number: "+919820011111",
  started_at: "2026-10-24T18:40:00.000Z",
  state: "ringing",
};

const mehta: LiveCall = {
  call_id: "call_mehta_1",
  tenant_id: "ten_mehta",
  tenant: "Mehta Dental",
  agent: "Reception",
  direction: "inbound",
  number: "+919876501111",
  started_at: "2026-10-24T18:41:00.000Z",
  state: "ringing",
};

const sagar: LiveCall = {
  call_id: "call_sagar_1",
  tenant_id: "ten_sagar",
  tenant: "Sagar Logistics",
  agent: "Collections",
  direction: "outbound",
  number: "+919811122222",
  started_at: "2026-10-24T18:39:30.000Z",
  state: "answered",
};

export const liveCallsFixture: {
  add: LiveFrame;
  remove: LiveFrame;
  snapshot: LiveFrame;
} = {
  add: { type: "call.created", call: aarohi },
  remove: { type: "call.ended", call_id: aarohi.call_id },
  snapshot: { type: "snapshot", calls: [mehta, sagar] },
};
