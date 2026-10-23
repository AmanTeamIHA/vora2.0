import Link from "next/link";
import { buttonVariants } from "@/components/ui/button";
import { cn } from "cn";

export default function Home() {
  return (
    <main className="mx-auto flex w-full max-w-xl flex-1 flex-col justify-center gap-6 px-6 py-16">
      <div>
        <p className="font-mono text-xs text-primary">DEV · ap-south-1</p>
        <h1 className="mt-2 text-3xl font-semibold tracking-tight">Vora 2.0</h1>
        <p className="mt-2 text-muted-foreground">
          One app, two areas. Super Admin runs the platform. A tenant sees only its own workspace.
        </p>
      </div>
      <div className="flex flex-wrap gap-3">
        <Link href="/admin" className={cn(buttonVariants())}>
          Super Admin
        </Link>
        <Link href="/t/demo" className={cn(buttonVariants({ variant: "outline" }))}>
          Tenant demo
        </Link>
      </div>
    </main>
  );
}
