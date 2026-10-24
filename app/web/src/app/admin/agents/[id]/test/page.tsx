"use client";

import Link from "next/link";
import { Room, RoomEvent, Track, type TranscriptionSegment } from "livekit-client";
import { useEffect, useRef, useState } from "react";
import { useParams } from "next/navigation";
import { Button } from "@/components/ui/button";

type Agent = {
  id: string;
  name: string;
  tenant_name: string;
  greeting: string;
};

type Turn = {
  eos_to_stt_final: number;
  llm_first_token: number;
  tts_first_byte: number;
  time_to_first_word: number;
};

type Line = { id: string; text: string; who: string };

const dot = {
  idle: "#86868B",
  connecting: "#FF9F0A",
  live: "#34C759",
  error: "#D70015",
} as const;

export default function TalkToAgentPage() {
  const params = useParams<{ id: string }>();
  const agentId = params.id;
  const [agent, setAgent] = useState<Agent | null>(null);
  const [status, setStatus] = useState<keyof typeof dot>("idle");
  const [error, setError] = useState("");
  const [lines, setLines] = useState<Line[]>([]);
  const [turns, setTurns] = useState<Turn[]>([]);
  const roomRef = useRef<Room | null>(null);
  const audioRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      const response = await fetch(`/api/admin/agents/${agentId}`, { credentials: "include" });
      const body = (await response.json().catch(() => ({}))) as Agent & { detail?: string };
      if (cancelled) return;
      if (!response.ok) {
        setError(typeof body.detail === "string" ? body.detail : "Could not load this agent");
        setStatus("error");
        return;
      }
      setAgent(body);
    }
    void load();
    return () => {
      cancelled = true;
      void roomRef.current?.disconnect();
    };
  }, [agentId]);

  async function hangUp() {
    await roomRef.current?.disconnect();
    roomRef.current = null;
    setStatus("idle");
  }

  async function talk() {
    setError("");
    setStatus("connecting");
    const response = await fetch(`/api/admin/agents/${agentId}/test-sessions`, {
      method: "POST",
      credentials: "include",
    });
    const body = (await response.json().catch(() => ({}))) as {
      detail?: string;
      url?: string;
      token?: string;
    };
    if (!response.ok || !body.url || !body.token) {
      setError(typeof body.detail === "string" ? body.detail : "Could not start the test");
      setStatus("error");
      return;
    }
    const room = new Room();
    roomRef.current = room;
    room.on(RoomEvent.TrackSubscribed, (track) => {
      if (track.kind !== Track.Kind.Audio || !audioRef.current) return;
      const element = track.attach();
      element.autoplay = true;
      audioRef.current.appendChild(element);
    });
    room.on(
      RoomEvent.TranscriptionReceived,
      (segments: TranscriptionSegment[], participant) => {
        setLines((current) => {
          const next = [...current];
          for (const segment of segments) {
            const who = participant?.isLocal ? "You" : "Agent";
            const index = next.findIndex((line) => line.id === segment.id);
            const line = { id: segment.id, text: segment.text, who };
            if (index >= 0) next[index] = line;
            else next.push(line);
          }
          return next;
        });
      },
    );
    room.on(RoomEvent.DataReceived, (payload, _participant, _kind, topic) => {
      if (topic !== "vora.turn") return;
      try {
        const turn = JSON.parse(new TextDecoder().decode(payload)) as Turn;
        if (typeof turn.time_to_first_word !== "number") return;
        setTurns((current) => [...current, turn].slice(-12));
      } catch {
        // Ignore a packet that is not a turn metric.
      }
    });
    room.on(RoomEvent.Disconnected, () => {
      setStatus((current) => (current === "error" ? current : "idle"));
    });
    try {
      await room.connect(body.url, body.token);
      await room.localParticipant.setMicrophoneEnabled(true);
      setStatus("live");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "The microphone or the room failed");
      setStatus("error");
      await room.disconnect();
    }
  }

  return (
    <div className="flex max-w-[760px] flex-col gap-6">
      <header>
        <Link href="/admin/agents" className="text-sm text-[#6E6E73] no-underline">
          Agents
        </Link>
        <div className="mt-2 flex items-center gap-3">
          <span
            className="inline-block size-2 rounded-full"
            style={{ background: dot[status] }}
            aria-hidden
          />
          <h1 className="text-[32px] leading-none font-semibold tracking-[-0.8px]">
            {agent?.name ?? "Agent"}
          </h1>
        </div>
        <p className="mt-2 text-sm text-[#6E6E73]">
          {agent?.tenant_name ? `${agent.tenant_name}. ` : ""}
          Talk here. The microphone stays in this browser. No phone line.
        </p>
      </header>

      <div className="flex gap-3">
        <Button
          type="button"
          onClick={() => void talk()}
          disabled={status === "connecting" || status === "live"}
        >
          Talk to agent
        </Button>
        {status === "live" ? (
          <Button type="button" variant="outline" onClick={() => void hangUp()}>
            Hang up
          </Button>
        ) : null}
      </div>
      {error ? <p className="text-sm text-[#D70015]">{error}</p> : null}

      <section className="rounded-2xl bg-white p-4 shadow-[0_0_0_1px_rgba(0,0,0,0.04)]">
        <h2 className="text-sm font-medium text-[#1D1D1F]">Transcript</h2>
        <div ref={audioRef} className="sr-only" />
        {lines.length === 0 ? (
          <p className="mt-3 text-sm text-[#6E6E73]">
            {agent?.greeting
              ? `The agent should open with “${agent.greeting}”`
              : "The agent speaks first."}
          </p>
        ) : (
          <ol className="mt-3 flex flex-col gap-3">
            {lines.map((line) => (
              <li key={line.id}>
                <span className="text-xs text-[#86868B]">{line.who}</span>
                <p className="text-sm text-[#1D1D1F]">{line.text}</p>
              </li>
            ))}
          </ol>
        )}
      </section>

      <section className="rounded-2xl bg-white p-4 shadow-[0_0_0_1px_rgba(0,0,0,0.04)]">
        <h2 className="text-sm font-medium text-[#1D1D1F]">Latency</h2>
        <p className="mt-1 text-xs text-[#86868B]">Milliseconds, this call.</p>
        <table className="mt-3 w-full text-left text-sm tabular-nums">
          <thead className="text-xs text-[#86868B]">
            <tr>
              <th className="py-1 font-medium">End of speech to text</th>
              <th className="py-1 font-medium">First token</th>
              <th className="py-1 font-medium">First byte</th>
              <th className="py-1 font-medium">First word</th>
            </tr>
          </thead>
          <tbody>
            {turns.map((turn, index) => (
              <tr key={`${index}-${turn.time_to_first_word}`} className="border-t border-border">
                <td className="py-2">{turn.eos_to_stt_final}</td>
                <td className="py-2">{turn.llm_first_token}</td>
                <td className="py-2">{turn.tts_first_byte}</td>
                <td className="py-2">{turn.time_to_first_word}</td>
              </tr>
            ))}
            {turns.length === 0 ? (
              <tr>
                <td className="py-3 text-[#6E6E73]" colSpan={4}>
                  Turns show up here as the agent speaks.
                </td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </section>
    </div>
  );
}
