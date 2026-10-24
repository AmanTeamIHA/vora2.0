"use client";

import { useState } from "react";
import { VoraMark } from "@/components/vora-mark";

export function AskVora() {
  const [open, setOpen] = useState(false);

  return (
    <div className="pointer-events-none fixed bottom-6 right-8 z-20 flex flex-col items-end gap-2">
      {open ? (
        <p className="pointer-events-auto max-w-xs rounded-2xl bg-white px-4 py-3 text-sm text-[#424245] shadow-[0_8px_24px_rgba(0,0,0,0.12)]">
          Ask Vora is not connected on this build.
        </p>
      ) : null}
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        className="pointer-events-auto flex h-12 items-center gap-2.5 rounded-3xl border-none bg-[#1D1D1F] py-0 pr-[18px] pl-2 text-sm font-medium text-white shadow-[0_8px_24px_rgba(0,0,0,0.18)]"
      >
        <VoraMark size={32} inverted />
        Ask Vora
      </button>
    </div>
  );
}
