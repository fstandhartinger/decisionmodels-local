import { beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({ query: vi.fn() }));
vi.mock("@/lib/server-runtime.mjs", () => ({ getPool: () => ({ query: mocks.query }) }));

import { POST } from "@/app/local/api/licence/verify/route";
import { createLicenceKey, hashLicenceKey } from "@/lib/licence-core";

describe("licence verify route", () => {
  beforeEach(() => mocks.query.mockReset());

  it("normalizes the key prefix and base32 suffix, then verifies a generated key", async () => {
    const key = createLicenceKey(() => Buffer.alloc(20, 0xff));
    const storedHash = hashLicenceKey(key);
    mocks.query.mockResolvedValue({ rows: [{ key_hash: storedHash, status: "active", past_due_since: null, expires_at: null }] });

    for (const submitted of [`  dmlk_${key.slice(5).toLowerCase()}  `, key.toUpperCase()]) {
      const response = await POST(new Request("https://decisionmodels.io/local/api/licence/verify", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ key: submitted })
      }));

      expect(response.status).toBe(200);
      expect(await response.json()).toMatchObject({ valid: true, status: "active" });
    }
    expect(mocks.query.mock.calls).toHaveLength(2);
    expect(mocks.query.mock.calls[0][1]).toEqual([storedHash]);
    expect(mocks.query.mock.calls[1][1]).toEqual([storedHash]);
  });
});
