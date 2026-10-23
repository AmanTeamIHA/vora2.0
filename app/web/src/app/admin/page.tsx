import { PlatformControls } from "@/components/platform-controls";
import { SessionBar } from "@/components/session-bar";
import { StackStatus } from "@/components/stack-status";

export default function AdminHome() {
  return (
    <div className="flex flex-col gap-6">
      <header>
        <h1 className="text-2xl font-semibold">Overview</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Platform overview. Sign in is required before this page loads.
        </p>
      </header>
      <SessionBar />
      <PlatformControls />
      <StackStatus />
    </div>
  );
}
