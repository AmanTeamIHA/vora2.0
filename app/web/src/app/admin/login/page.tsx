"use client";

import { useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [code, setCode] = useState("");
  const [uri, setUri] = useState<string | null>(null);
  const [step, setStep] = useState<"password" | "totp">("password");
  const [error, setError] = useState("");

  async function submitPassword(event: FormEvent) {
    event.preventDefault();
    setError("");
    const response = await fetch("/api/auth/login", {
      method: "POST",
      headers: { "content-type": "application/json" },
      credentials: "include",
      body: JSON.stringify({ email, password }),
    });
    if (!response.ok) {
      const failure = (await response.json().catch(() => null)) as { detail?: string } | null;
      setError(failure?.detail ?? "Email or password is wrong");
      return;
    }
    const body = (await response.json()) as { provisioning_uri?: string };
    setUri(body.provisioning_uri ?? null);
    setStep("totp");
  }

  async function submitCode(event: FormEvent) {
    event.preventDefault();
    setError("");
    const response = await fetch("/api/auth/totp", {
      method: "POST",
      headers: { "content-type": "application/json" },
      credentials: "include",
      body: JSON.stringify({ code }),
    });
    if (!response.ok) {
      setError("Code is wrong");
      return;
    }
    router.push("/admin");
  }

  return (
    <div className="mx-auto flex w-full max-w-md flex-col gap-4">
      <h1 className="text-2xl font-semibold">Sign in</h1>
      <p className="text-sm text-muted-foreground">
        Super Admin sign-in uses a password and an authenticator code.
      </p>
      {step === "password" ? (
        <form className="flex flex-col gap-3" onSubmit={submitPassword}>
          <label className="flex flex-col gap-1 text-sm">
            Email
            <input
              className="h-11 rounded-lg border border-border bg-card px-3"
              type="email"
              autoComplete="username"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              required
            />
          </label>
          <label className="flex flex-col gap-1 text-sm">
            Password
            <input
              className="h-11 rounded-lg border border-border bg-card px-3"
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              required
            />
          </label>
          <Button type="submit">Continue</Button>
        </form>
      ) : (
        <form className="flex flex-col gap-3" onSubmit={submitCode}>
          {uri ? (
            <p className="break-all rounded-lg bg-card p-3 font-mono text-xs">{uri}</p>
          ) : null}
          <label className="flex flex-col gap-1 text-sm">
            Authenticator code
            <input
              className="h-11 rounded-lg border border-border bg-card px-3"
              inputMode="numeric"
              autoComplete="one-time-code"
              value={code}
              onChange={(event) => setCode(event.target.value)}
              required
            />
          </label>
          <Button type="submit">Sign in</Button>
        </form>
      )}
      {error ? <p className="text-sm text-destructive">{error}</p> : null}
    </div>
  );
}
