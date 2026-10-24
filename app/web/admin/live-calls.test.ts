import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { liveCallsFixture } from "./live-calls-fixture.ts";
import {
  applyLiveFrame,
  connectLiveCalls,
  filterCalls,
  formatDuration,
  liveCallsWebSocketUrl,
  parseLiveFrame,
  reconnectDelayMs,
  rememberTenants,
  sortLiveCalls,
  type LiveCall,
  type LiveFrame,
  type LiveSocket,
} from "./live-calls.ts";

describe("live call fixture", () => {
  it("adds a row from the fixture and removes it when the call ends", () => {
    const added = parseLiveFrame(JSON.stringify(liveCallsFixture.add));
    const removed = parseLiveFrame(JSON.stringify(liveCallsFixture.remove));
    assert.ok(added);
    assert.ok(removed);

    let rows: LiveCall[] = [];
    rows = applyLiveFrame(rows, added);
    assert.equal(rows.length, 1);
    assert.equal(rows[0]?.call_id, "call_aarohi_1");
    assert.equal(rows[0]?.tenant, "Aarohi Clinics");
    assert.equal(rows[0]?.agent, "Reception");
    assert.equal(rows[0]?.direction, "inbound");
    assert.equal(rows[0]?.number, "+919820011111");
    assert.equal(rows[0]?.state, "ringing");

    rows = applyLiveFrame(rows, removed);
    assert.deepEqual(rows, []);
  });

  it("feeds the fixture through the socket, then reconnects after the socket drops", () => {
    const sockets: FakeSocket[] = [];
    const pending: Array<() => void> = [];
    const frames: LiveFrame[] = [];
    const statuses: string[] = [];

    const stop = connectLiveCalls({
      url: "ws://127.0.0.1:8000/admin/live-calls",
      onFrame: (frame) => frames.push(frame),
      onStatus: (status) => statuses.push(status),
      openSocket: (url) => {
        const socket = new FakeSocket(url);
        sockets.push(socket);
        return socket;
      },
      schedule: (fn) => {
        pending.push(fn);
        return {
          cancel() {
            const index = pending.indexOf(fn);
            if (index >= 0) pending.splice(index, 1);
          },
        };
      },
      delay: () => 250,
    });

    assert.equal(sockets.length, 1);
    assert.equal(statuses.at(-1), "connecting");
    sockets[0]?.emitOpen();
    assert.equal(statuses.at(-1), "live");
    sockets[0]?.emitMessage(JSON.stringify(liveCallsFixture.add));
    sockets[0]?.emitMessage(JSON.stringify(liveCallsFixture.remove));

    let rows = frames.reduce(applyLiveFrame, [] as LiveCall[]);
    assert.deepEqual(rows, []);
    assert.equal(frames.length, 2);

    sockets[0]?.emitClose(1006);
    assert.equal(statuses.at(-1), "reconnecting");
    assert.equal(pending.length, 1);
    pending.shift()?.();
    assert.equal(sockets.length, 2);
    sockets[1]?.emitOpen();
    sockets[1]?.emitMessage(JSON.stringify(liveCallsFixture.snapshot));
    rows = frames.reduce(applyLiveFrame, [] as LiveCall[]);
    assert.equal(rows.length, 2);

    stop();
    sockets[1]?.emitClose(1000);
    assert.equal(pending.length, 0);
    assert.equal(sockets.length, 2);
  });
});

describe("live call frames", () => {
  it("replaces rows from a snapshot and drops ended calls", () => {
    const snapshot = parseLiveFrame(
      JSON.stringify({
        type: "snapshot",
        calls: [
          liveCallsFixture.snapshot.type === "snapshot" ? liveCallsFixture.snapshot.calls[0] : null,
          {
            call_id: "call_done",
            tenant: "Mehta Dental",
            agent: "Reception",
            direction: "inbound",
            number: "+919800000000",
            started_at: "2026-10-24T18:00:00.000Z",
            state: "ended",
          },
        ],
      }),
    );
    assert.equal(snapshot?.type, "snapshot");
    if (snapshot?.type !== "snapshot") return;
    assert.equal(snapshot.calls.length, 1);
    assert.equal(snapshot.calls[0]?.call_id, "call_mehta_1");
  });

  it("updates state in place and ignores a bad payload", () => {
    const created = parseLiveFrame(JSON.stringify(liveCallsFixture.add));
    assert.ok(created);
    const answered = parseLiveFrame(
      JSON.stringify({
        event: "call.answered",
        call: {
          ...(liveCallsFixture.add.type === "call.created" ? liveCallsFixture.add.call : {}),
          state: "answered",
        },
      }),
    );
    assert.ok(answered);
    let rows = applyLiveFrame([], created);
    rows = applyLiveFrame(rows, answered);
    assert.equal(rows.length, 1);
    assert.equal(rows[0]?.state, "answered");
    assert.equal(parseLiveFrame("not-json"), null);
    assert.equal(parseLiveFrame(JSON.stringify({ type: "transcript" })), null);
  });

  it("narrows rows with the tenant filter", () => {
    const snapshot = parseLiveFrame(JSON.stringify(liveCallsFixture.snapshot));
    assert.ok(snapshot);
    const rows = applyLiveFrame([], snapshot);
    const mehta = filterCalls(rows, "ten_mehta");
    assert.equal(mehta.length, 1);
    assert.equal(mehta[0]?.tenant, "Mehta Dental");
    assert.equal(filterCalls(rows, "").length, 2);
    const choices = rememberTenants([], rows);
    assert.deepEqual(
      choices.map((choice) => choice.label),
      ["Mehta Dental", "Sagar Logistics"],
    );
  });

  it("sorts newer calls first and formats a ticking duration", () => {
    const snapshot = parseLiveFrame(JSON.stringify(liveCallsFixture.snapshot));
    assert.ok(snapshot);
    const rows = sortLiveCalls(applyLiveFrame([], snapshot));
    assert.deepEqual(
      rows.map((row) => row.call_id),
      ["call_mehta_1", "call_sagar_1"],
    );
    const start = "2026-10-24T18:40:00.000Z";
    assert.equal(formatDuration(start, Date.parse("2026-10-24T18:40:05.000Z")), "0:05");
    assert.equal(formatDuration(start, Date.parse("2026-10-24T18:41:05.000Z")), "1:05");
    assert.equal(formatDuration(start, Date.parse("2026-10-24T19:41:01.000Z")), "1:01:01");
    assert.equal(formatDuration(start, Date.parse("2026-10-24T18:39:00.000Z")), "0:00");
    assert.equal(formatDuration("nope", 0), "—");
  });

  it("builds the socket url for playground and for a local API", () => {
    assert.equal(
      liveCallsWebSocketUrl("https://playground-dev.hellovora.ai/api"),
      "wss://playground-dev.hellovora.ai/api/admin/live-calls",
    );
    assert.equal(liveCallsWebSocketUrl("http://127.0.0.1:8000"), "ws://127.0.0.1:8000/admin/live-calls");
    assert.equal(
      liveCallsWebSocketUrl("", "https://playground-dev.hellovora.ai"),
      "wss://playground-dev.hellovora.ai/api/admin/live-calls",
    );
  });

  it("backs off and stops reconnecting when the socket is refused", () => {
    assert.equal(reconnectDelayMs(0), 500);
    assert.equal(reconnectDelayMs(1), 1000);
    assert.equal(reconnectDelayMs(9), 15000);

    const sockets: FakeSocket[] = [];
    const pending: Array<() => void> = [];
    const statuses: string[] = [];
    connectLiveCalls({
      url: "ws://example.test/admin/live-calls",
      onFrame: () => undefined,
      onStatus: (status) => statuses.push(status),
      openSocket: (url) => {
        const socket = new FakeSocket(url);
        sockets.push(socket);
        return socket;
      },
      schedule: (fn) => {
        pending.push(fn);
        return { cancel() {} };
      },
    });
    sockets[0]?.emitClose(4403);
    assert.equal(statuses.at(-1), "unavailable");
    assert.equal(pending.length, 0);
    assert.equal(sockets.length, 1);
  });
});

class FakeSocket implements LiveSocket {
  onopen: (() => void) | null = null;
  onmessage: ((event: { data: string }) => void) | null = null;
  onclose: ((event: { code: number }) => void) | null = null;
  onerror: (() => void) | null = null;
  closed = false;
  url: string;

  constructor(url: string) {
    this.url = url;
  }

  close() {
    this.closed = true;
    this.onclose?.({ code: 1000 });
  }

  emitOpen() {
    this.onopen?.();
  }

  emitMessage(data: string) {
    this.onmessage?.({ data });
  }

  emitClose(code: number) {
    this.onclose?.({ code });
  }
}
