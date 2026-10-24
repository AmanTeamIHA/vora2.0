"use client";

import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";

export function ShellHeader() {
  const router = useRouter();
  const [query, setQuery] = useState("");

  function search(event: FormEvent) {
    event.preventDefault();
    const value = query.trim();
    router.push(value ? `/admin/tenants?q=${encodeURIComponent(value)}` : "/admin/tenants");
  }

  return (
    <header className="flex h-16 items-center gap-4 border-b border-[#E8E8ED] bg-white/80 px-8">
      <form onSubmit={search} className="flex h-[38px] w-full max-w-80 items-center gap-2 rounded-[10px] bg-[#F0F0F2] px-3">
        <label htmlFor="vora-search" className="sr-only">
          Search
        </label>
        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="#86868B" strokeWidth="2" strokeLinecap="round" aria-hidden="true">
          <circle cx="11" cy="11" r="7" />
          <path d="M20 20l-3.5-3.5" />
        </svg>
        <input
          id="vora-search"
          type="search"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Search tenants"
          className="min-w-0 flex-1 border-none bg-transparent text-sm text-[#1D1D1F] outline-none"
        />
      </form>
    </header>
  );
}
