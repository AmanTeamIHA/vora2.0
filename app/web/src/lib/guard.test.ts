import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { adminNeedsLogin } from "./guard.ts";

describe("admin route guard", () => {
  it("sends an unsigned visitor to login", () => {
    assert.equal(adminNeedsLogin("/admin", false), true);
    assert.equal(adminNeedsLogin("/admin/login", false), false);
  });

  it("lets a signed-in cookie through", () => {
    assert.equal(adminNeedsLogin("/admin", true), false);
  });
});
