"use client";

import { useEffect, useState, useSyncExternalStore } from "react";
import { liveCallsFixture } from "./live-calls-fixture";
import {
  applyLiveFrame,
  connectLiveCalls,
  filterCalls,
  formatDuration,
  liveCallsWebSocketUrl,
  rememberTenants,
  sortLiveCalls,
  type LiveCall,
  type LiveConnectionStatus,
  type TenantChoice,
} from "./live-calls";

const columns = ["Tenant", "Agent", "Direction", "Number", "Duration", "State"] as const;

const fixtureCalls = applyLiveFrame([], liveCallsFixture.snapshot);

function directionLabel(direction: LiveCall["direction"]): string {
  return direction === "inbound" ? "Inbound" : "Outbound";
}

function stateLabel(state: LiveCall["state"]): string {
  if (state === "created") return "Created";
  if (state === "ringing") return "Ringing";
  return "Answered";
}

let clientNow: number | null = null;

function subscribeClock(onChange: () => void) {
  const id = setInterval(() => {
    clientNow = Date.now();
    onChange();
  }, 1000);
  return () => clearInterval(id);
}

function readClock(): number | null {
  if (clientNow === null) clientNow = Date.now();
  return clientNow;
}

function serverClock(): number | null {
  return null;
}

function useTickingNow(): number | null {
  return useSyncExternalStore(subscribeClock, readClock, serverClock);
}

function statusLabel(status: LiveConnectionStatus, fixture: boolean): string {
  if (fixture) return "Test data";
  if (status === "live") return "Live";
  if (status === "reconnecting") return "Reconnecting…";
  if (status === "unavailable") return "Live calls are not available for this account.";
  return "Connecting…";
}

type Board = { calls: LiveCall[]; choices: TenantChoice[] };

const emptyBoard: Board = { calls: [], choices: [] };

function withFrame(board: Board, frame: Parameters<typeof applyLiveFrame>[1]): Board {
  const calls = applyLiveFrame(board.calls, frame);
  return { calls, choices: rememberTenants(board.choices, calls) };
}

export function LiveCallsView({ fixture }: { fixture: boolean }) {
  const [board, setBoard] = useState<Board>(emptyBoard);
  const [tenant, setTenant] = useState("");
  const [status, setStatus] = useState<LiveConnectionStatus>("connecting");
  const now = useTickingNow();

  const source = fixture ? fixtureCalls : board.calls;
  const choices = fixture ? rememberTenants([], fixtureCalls) : board.choices;
  const visible = sortLiveCalls(filterCalls(source, tenant));
  const empty = tenant ? "No live calls for this tenant." : "No live calls.";

  useEffect(() => {
    if (fixture) return;
    const url = liveCallsWebSocketUrl(process.env.NEXT_PUBLIC_API_URL ?? "", window.location.origin);
    return connectLiveCalls({
      url,
      onStatus: setStatus,
      onFrame: (frame) => {
        setBoard((current) => withFrame(current, frame));
      },
    });
  }, [fixture]);

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-col gap-1.5">
        <h1 className="text-[32px] leading-none font-semibold tracking-[-0.8px]">Live calls</h1>
        <p className="text-[15px] text-[#6E6E73]" role="status">
          {statusLabel(status, fixture)}
          <span className="tabular-nums"> · {visible.length} showing</span>
        </p>
      </div>

      <label className="flex max-w-xs flex-col gap-1 text-sm text-[#424245]">
        Tenant
        <select
          className="h-10 rounded-lg border border-[#E8E8ED] bg-white px-3 text-sm text-[#1D1D1F]"
          value={tenant}
          onChange={(event) => setTenant(event.target.value)}
        >
          <option value="">All tenants</option>
          {choices.map((choice) => (
            <option key={choice.key} value={choice.key}>
              {choice.label}
            </option>
          ))}
        </select>
      </label>

      <section className="rounded-2xl bg-white px-[22px] pt-[22px] pb-3 shadow-[0_0_0_1px_rgba(0,0,0,0.04)]">
        <div className="overflow-x-auto">
          <table className="w-full min-w-[760px] border-collapse text-sm">
            <caption className="sr-only">Live calls</caption>
            <thead>
              <tr className="text-left text-xs font-normal text-[#86868B]">
                {columns.map((column) => (
                  <th key={column} scope="col" className="py-2.5 font-normal">
                    {column}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {visible.length === 0 ? (
                <tr>
                  <td colSpan={columns.length} className="border-t border-[#F0F0F2] py-3 text-[#6E6E73]">
                    {empty}
                  </td>
                </tr>
              ) : (
                visible.map((call) => (
                  <tr key={call.call_id} data-call-id={call.call_id} className="hover:bg-[#FAFAFA]">
                    <td className="border-t border-[#F0F0F2] py-3 pr-3 font-medium">{call.tenant}</td>
                    <td className="border-t border-[#F0F0F2] py-3 pr-3 text-[#424245]">{call.agent}</td>
                    <td className="border-t border-[#F0F0F2] py-3 pr-3 text-[#424245]">
                      {directionLabel(call.direction)}
                    </td>
                    <td className="border-t border-[#F0F0F2] py-3 pr-3 font-mono text-[13px] text-[#424245] tabular-nums">
                      {call.number}
                    </td>
                    <td className="border-t border-[#F0F0F2] py-3 pr-3 text-[#1D1D1F] tabular-nums">
                      {now === null ? "—" : formatDuration(call.started_at, now)}
                    </td>
                    <td className="border-t border-[#F0F0F2] py-3 text-[#424245]">{stateLabel(call.state)}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
