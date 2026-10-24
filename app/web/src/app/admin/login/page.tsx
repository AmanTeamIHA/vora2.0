"use client";

import { useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
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
    router.push("/admin");
  }

  return (
    <div className="mx-auto flex w-full max-w-md flex-col gap-4 rounded-2xl bg-white p-8 shadow-[0_0_0_1px_rgba(0,0,0,0.04)]">
      <h1 className="text-[32px] leading-none font-semibold tracking-[-0.8px]">Sign in</h1>
      <p className="text-sm text-[#6E6E73]">Sign in with your email and password.</p>
      <form className="flex flex-col gap-3" onSubmit={submitPassword}>
        <label className="flex flex-col gap-1 text-sm">
          Email
          <input
            className="h-11 rounded-[10px] border border-[#E8E8ED] bg-white px-3"
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
            className="h-11 rounded-[10px] border border-[#E8E8ED] bg-white px-3"
            type="password"
            autoComplete="current-password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            required
          />
        </label>
        <Button type="submit">Sign in</Button>
      </form>
      {error ? <p className="text-sm text-[#D70015]">{error}</p> : null}
    </div>
  );
}
