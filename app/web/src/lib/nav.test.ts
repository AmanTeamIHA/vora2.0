import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { adminNav, navIsActive, tenantNav } from "./nav.ts";

describe("role layouts", () => {
  it("keeps Super Admin navigation on /admin", () => {
    assert.equal(adminNav[0]?.href, "/admin");
    assert.equal(
      adminNav.every((item) => item.href.startsWith("/admin")),
      true,
    );
    assert.equal(
      adminNav.some((item) => item.href.startsWith("/t/")),
      false,
    );
    assert.equal(navIsActive("/admin/tenants", "/admin", adminNav), false);
    assert.equal(navIsActive("/admin/tenants", "/admin/tenants", adminNav), true);
  });

  it("scopes a tenant shell to that tenant", () => {
    const items = tenantNav("acme");
    assert.equal(
      items.every((item) => item.href.startsWith("/t/acme")),
      true,
    );
    assert.equal(
      items.some((item) => item.label === "Overview"),
      false,
    );
  });
});
