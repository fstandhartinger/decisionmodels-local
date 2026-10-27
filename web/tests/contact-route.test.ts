import { beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({ query: vi.fn(), retryMail: vi.fn() }));
vi.mock("@/lib/server-runtime.mjs", () => ({
  getPool: () => ({ query: mocks.query }),
  retryHardwareInquiryMail: mocks.retryMail
}));
vi.mock("@/lib/server/rate-limit", () => ({ requestIp: () => "127.0.0.1", checkContactRateLimit: () => ({ allowed: true }) }));
import { POST } from "@/app/local/api/contact/route";

const payload = { name: "Taylor Smith", email: "taylor@example.com", models: ["pplx-decider-v1-1-27b"], quantity: 1, location: "office", timeline: "researching", consent: true };
function submit(body: object) {
  return POST(new Request("http://localhost/local/api/contact", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body) }));
}

beforeEach(() => {
  vi.clearAllMocks();
  mocks.query.mockResolvedValueOnce({ rows: [{ id: "inquiry-test" }] }).mockResolvedValueOnce({ rows: [{ mail_sent_at: null }] });
});

describe("hardware contact POST", () => {
  it("stores an unknown requested model in the models array and queues its mail", async () => {
    const response = await submit(payload);
    expect(response.status).toBe(200);
    expect(await response.json()).toEqual({ ok: true, mail: "queued" });
    expect(mocks.query.mock.calls[0][0]).toContain("INSERT INTO hardware_inquiries");
    expect(mocks.query.mock.calls[0][1][3]).toEqual(payload.models);
    expect(mocks.retryMail).toHaveBeenCalledOnce();
  });
  it.each([{ models: ["../model"] }, { models: Array(21).fill("valid-slug") }, { consent: false }])("rejects invalid inquiries before storage: %j", async (invalid) => {
    expect((await submit({ ...payload, ...invalid })).status).toBe(400);
    expect(mocks.query).not.toHaveBeenCalled();
    expect(mocks.retryMail).not.toHaveBeenCalled();
  });
  it("keeps honeypot submissions out of storage", async () => {
    expect((await submit({ ...payload, website: "bot" })).status).toBe(200);
    expect(mocks.query).not.toHaveBeenCalled();
    expect(mocks.retryMail).not.toHaveBeenCalled();
  });
});
