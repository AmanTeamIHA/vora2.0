import { StackStatus } from "@/components/stack-status";

export default function AdminHome() {
  return (
    <div className="flex flex-col gap-6">
      <header>
        <h1 className="text-2xl font-semibold">Overview</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Super Admin shell. Sign-in and roles arrive in a later ticket.
        </p>
      </header>
      <StackStatus />
    </div>
  );
}
