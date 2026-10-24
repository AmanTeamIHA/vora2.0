"use client";

import { useEffect, useState, type FormEvent } from "react";
import { Button } from "@/components/ui/button";

type Person = {
  id: string;
  email: string;
  full_name: string;
  disabled: boolean;
  roles: string[];
};

type Tenant = { id: string; name: string };

const platformRoles = ["Owner", "Platform Admin", "Support", "Finance", "Read-only"];
const tenantRoles = ["Tenant Admin", "Manager", "Agent Builder", "Human Agent", "Viewer"];

export default function UsersPage() {
  const [scope, setScope] = useState("");
  const [tenants, setTenants] = useState<Tenant[]>([]);
  const [people, setPeople] = useState<Person[]>([]);
  const [email, setEmail] = useState("");
  const [fullName, setFullName] = useState("");
  const [roleName, setRoleName] = useState("Support");
  const [canWrite, setCanWrite] = useState(false);
  const [invite, setInvite] = useState("");
  const [error, setError] = useState("");

  const roles = scope ? tenantRoles : platformRoles;

  async function load(nextScope: string) {
    const params = nextScope ? `?tenant_id=${nextScope}` : "";
    const response = await fetch(`/api/admin/users${params}`, { credentials: "include" });
    if (!response.ok) return;
    const body = (await response.json()) as { users: Person[] };
    setPeople(body.users);
  }

  useEffect(() => {
    let cancelled = false;
    async function run() {
      const [me, tenantBody] = await Promise.all([
        fetch("/api/auth/me", { credentials: "include" }).then((response) => response.json()),
        fetch("/api/admin/tenants", { credentials: "include" }).then((response) => response.json()),
      ]);
      if (cancelled) return;
      setCanWrite(Boolean((me as { can_write?: boolean }).can_write));
      setTenants((tenantBody as { tenants?: Tenant[] }).tenants ?? []);
      await load("");
    }
    void run();
    return () => {
      cancelled = true;
    };
  }, []);

  async function inviteUser(event: FormEvent) {
    event.preventDefault();
    setError("");
    const response = await fetch("/api/admin/users", {
      method: "POST",
      headers: { "content-type": "application/json" },
      credentials: "include",
      body: JSON.stringify({
        email,
        full_name: fullName,
        role_name: roleName,
        tenant_id: scope || null,
      }),
    });
    const body = (await response.json()) as { detail?: string; invite?: { token: string } };
    if (!response.ok) {
      setError(body.detail ?? "Could not invite this user");
      return;
    }
    setInvite(body.invite?.token ?? "");
    setEmail("");
    setFullName("");
    await load(scope);
  }

  async function setDisabled(id: string, disabled: boolean) {
    setError("");
    const action = disabled ? "disable" : "enable";
    const response = await fetch(`/api/admin/users/${id}/${action}`, {
      method: "POST",
      credentials: "include",
    });
    if (!response.ok) {
      setError("Could not update this user");
      return;
    }
    await load(scope);
  }

  return (
    <div className="flex flex-col gap-6">
      <header>
        <h1 className="text-[32px] leading-none font-semibold tracking-[-0.8px]">Users & roles</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          IHA platform users, and the people inside each tenant. Disabling an account blocks sign-in.
        </p>
      </header>
      <label className="flex max-w-xs flex-col gap-1 text-sm">
        Workspace
        <select
          className="h-10 rounded-lg border border-border bg-card px-3"
          value={scope}
          onChange={(event) => {
            setScope(event.target.value);
            setRoleName(event.target.value ? "Tenant Admin" : "Support");
            void load(event.target.value);
          }}
          aria-label="Workspace"
        >
          <option value="">IHA platform</option>
          {tenants.map((tenant) => (
            <option key={tenant.id} value={tenant.id}>
              {tenant.name}
            </option>
          ))}
        </select>
      </label>
      {invite ? (
        <p className="break-all rounded-lg border border-border bg-card p-3 text-sm">
          Invite token (shown once): {invite}
        </p>
      ) : null}
      <div className="overflow-x-auto rounded-2xl bg-white shadow-[0_0_0_1px_rgba(0,0,0,0.04)]">
        <table className="w-full min-w-[640px] text-left text-sm">
          <thead className="text-xs font-normal text-[#86868B]">
            <tr>
              <th className="px-3 py-2 font-medium">Name</th>
              <th className="px-3 py-2 font-medium">Email</th>
              <th className="px-3 py-2 font-medium">Roles</th>
              <th className="px-3 py-2 font-medium">Status</th>
              {canWrite ? <th className="px-3 py-2 font-medium">Actions</th> : null}
            </tr>
          </thead>
          <tbody>
            {people.map((person) => (
              <tr key={person.id} className="border-t border-border">
                <td className="px-3 py-2">{person.full_name}</td>
                <td className="px-3 py-2">{person.email}</td>
                <td className="px-3 py-2">{person.roles.join(", ")}</td>
                <td className="px-3 py-2">{person.disabled ? "Disabled" : "Active"}</td>
                {canWrite ? (
                  <td className="px-3 py-2">
                    <Button
                      type="button"
                      variant="outline"
                      onClick={() => void setDisabled(person.id, !person.disabled)}
                    >
                      {person.disabled ? "Enable" : "Disable"}
                    </Button>
                  </td>
                ) : null}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {canWrite ? (
        <form className="grid max-w-xl gap-3" onSubmit={inviteUser}>
          <h2 className="text-lg font-semibold">Invite</h2>
          <label className="flex flex-col gap-1 text-sm">
            Name
            <input
              className="h-11 rounded-lg border border-border bg-card px-3"
              value={fullName}
              onChange={(event) => setFullName(event.target.value)}
              required
            />
          </label>
          <label className="flex flex-col gap-1 text-sm">
            Email
            <input
              className="h-11 rounded-lg border border-border bg-card px-3"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              required
            />
          </label>
          <label className="flex flex-col gap-1 text-sm">
            Role
            <select
              className="h-11 rounded-lg border border-border bg-card px-3"
              value={roleName}
              onChange={(event) => setRoleName(event.target.value)}
            >
              {roles.map((role) => (
                <option key={role} value={role}>
                  {role}
                </option>
              ))}
            </select>
          </label>
          <Button type="submit">Send invite</Button>
        </form>
      ) : (
        <p className="text-sm text-muted-foreground">This role can view users and cannot change them.</p>
      )}
      {error ? <p className="text-sm text-destructive">{error}</p> : null}
    </div>
  );
}
