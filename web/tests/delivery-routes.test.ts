import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({ claimQuery: vi.fn(), databaseQuery: vi.fn() }));
vi.mock("@/lib/server-runtime.mjs", () => ({
  decryptMessage: vi.fn(),
  getPool: () => ({
    connect: async () => ({ query: mocks.claimQuery, release: vi.fn() }),
    query: mocks.databaseQuery
  })
}));

import { GET } from "@/app/local/api/licence/delivery/route";
import { POST as openPortal } from "@/app/local/api/portal/route";

const originalStripeKey = process.env.STRIPE_SECRET_KEY;
afterEach(() => {
  if (originalStripeKey === undefined) delete process.env.STRIPE_SECRET_KEY;
  else process.env.STRIPE_SECRET_KEY = originalStripeKey;
});

describe("licence delivery and portal expiry", () => {
  beforeEach(() => {
    mocks.claimQuery.mockReset();
    mocks.databaseQuery.mockReset();
    mocks.claimQuery.mockResolvedValue({ rows: [] });
    mocks.databaseQuery.mockResolvedValue({ rows: [] });
  });

  it("returns pending while the payment webhook has not created the delivery", async () => {
    const response = await GET(new Request("https://decisionmodels.io/local/api/licence/delivery?session_id=cs_test_123"));
    expect(response.status).toBe(202);
    expect(response.headers.get("retry-after")).toBe("2");
    expect(await response.json()).toEqual({ pending: true });
  });

  it("expires billing portal access one hour after licence creation", async () => {
    mocks.databaseQuery.mockResolvedValue({ rows: [{ customer_id: "cus_123", status: "active", created_at: new Date(Date.now() - 2 * 60 * 60 * 1000) }] });
    process.env.STRIPE_SECRET_KEY = "sk_test_portal_expiry";
    const response = await openPortal(new Request("https://decisionmodels.io/local/api/portal", {
      method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ session_id: "cs_test_123" })
    }));
    expect(response.status).toBe(410);
    expect(await response.json()).toMatchObject({ error: "portal_link_expired" });
  });
});
