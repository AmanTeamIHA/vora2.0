"use client";

import { useEffect, useState, type FormEvent } from "react";
import { Button } from "@/components/ui/button";

type Sarvam = {
  api_key_set: boolean;
  api_key_last4: string;
  env_fallback: boolean;
  stt_model: string;
  tts_model: string;
  llm_model: string;
};

const field =
  "h-10 w-full rounded-lg border border-[#E8E8ED] bg-white px-3 text-sm text-[#1D1D1F] outline-none focus:border-[#1D1D1F]";

export default function IntegrationsPage() {
  const [sarvam, setSarvam] = useState<Sarvam | null>(null);
  const [apiKey, setApiKey] = useState("");
  const [canWrite, setCanWrite] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  useEffect(() => {
    let cancelled = false;
    async function run() {
      const me = (await fetch("/api/auth/me", { credentials: "include" }).then((response) =>
        response.json(),
      )) as { can_write?: boolean };
      if (cancelled) return;
      const allowed = Boolean(me.can_write);
      setCanWrite(allowed);
      if (!allowed) {
        setLoaded(true);
        return;
      }
      const response = await fetch("/api/admin/settings/integrations", { credentials: "include" });
      const body = (await response.json().catch(() => ({}))) as {
        sarvam?: Sarvam;
        detail?: string;
      };
      if (cancelled) return;
      if (!response.ok || !body.sarvam) {
        setError(typeof body.detail === "string" ? body.detail : "Could not load integrations");
        setLoaded(true);
        return;
      }
      setSarvam(body.sarvam);
      setLoaded(true);
    }
    void run().catch(() => {
      if (!cancelled) {
        setError("Could not load integrations");
        setLoaded(true);
      }
    });
    return () => {
      cancelled = true;
    };
  }, []);

  function setModel(key: "stt_model" | "tts_model" | "llm_model", value: string) {
    setSarvam((current) => (current ? { ...current, [key]: value } : current));
  }

  async function save(event: FormEvent) {
    event.preventDefault();
    if (!sarvam) return;
    setError("");
    setNotice("");
    const payload: Record<string, string> = {
      stt_model: sarvam.stt_model,
      tts_model: sarvam.tts_model,
      llm_model: sarvam.llm_model,
    };
    if (apiKey.trim()) payload.api_key = apiKey.trim();
    const response = await fetch("/api/admin/settings/integrations/sarvam", {
      method: "PUT",
      headers: { "content-type": "application/json" },
      credentials: "include",
      body: JSON.stringify(payload),
    });
    const body = (await response.json().catch(() => ({}))) as {
      sarvam?: Sarvam;
      detail?: string;
    };
    if (!response.ok || !body.sarvam) {
      setError(typeof body.detail === "string" ? body.detail : "Could not save Sarvam");
      return;
    }
    setSarvam(body.sarvam);
    setApiKey("");
    setNotice("Saved");
  }

  const savedKey = sarvam?.api_key_set
    ? `Saved key ends in ${sarvam.api_key_last4}`
    : "No key saved";

  return (
    <div className="flex flex-col gap-6">
      <header>
        <h1 className="text-[32px] leading-none font-semibold tracking-[-0.8px]">Global Settings</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Integrations for the whole platform. Owner and Platform Admin only.
        </p>
      </header>
      {loaded && !canWrite ? (
        <p className="text-sm text-[#6E6E73]">Owner or Platform Admin access is required.</p>
      ) : null}
      {canWrite && sarvam ? (
        <form
          className="flex max-w-xl flex-col gap-4 rounded-2xl bg-white p-5 shadow-[0_0_0_1px_rgba(0,0,0,0.04)]"
          onSubmit={save}
        >
          <div>
            <h2 className="text-lg font-semibold">Integrations</h2>
            <p className="mt-1 text-sm text-[#6E6E73]">
              Sarvam supplies speech recognition, the conversation model, and the voice.
            </p>
          </div>
          <label className="flex flex-col gap-1.5 text-sm">
            <span className="text-[#6E6E73]">Sarvam API key</span>
            <input
              className={field}
              type="password"
              name="sarvam-api-key"
              autoComplete="off"
              spellCheck={false}
              value={apiKey}
              placeholder="Paste a new key"
              onChange={(event) => setApiKey(event.target.value)}
            />
            <span className="text-xs text-[#86868B]">
              {savedKey}. Leave this blank to keep it. The full key is never shown again.
              {sarvam.env_fallback
                ? " Until a key is saved, the worker can use SARVAM_API_KEY from the environment."
                : ""}
            </span>
          </label>
          {(
            [
              ["stt_model", "STT model"],
              ["tts_model", "TTS model"],
              ["llm_model", "LLM model"],
            ] as const
          ).map(([key, label]) => (
            <label key={key} className="flex flex-col gap-1.5 text-sm">
              <span className="text-[#6E6E73]">{label}</span>
              <input
                className={field}
                value={sarvam[key]}
                onChange={(event) => setModel(key, event.target.value)}
                required
              />
            </label>
          ))}
          <Button type="submit">Save Sarvam</Button>
        </form>
      ) : null}
      {error ? <p className="text-sm text-[#D70015]">{error}</p> : null}
      {notice ? <p className="text-sm text-[#6E6E73]">{notice}</p> : null}
    </div>
  );
}
