import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({ query: vi.fn(), sendMail: vi.fn() }));
vi.mock("pg", () => ({ default: { Pool: class { query = mocks.query; } } }));
vi.mock("nodemailer", () => ({ default: { createTransport: () => ({ sendMail: mocks.sendMail }) } }));
import { retryHardwareInquiryMail } from "../lib/server-runtime.mjs";

beforeEach(() => vi.clearAllMocks());
afterEach(() => vi.unstubAllEnvs());

describe("hardware inquiry emails", () => {
  it("includes the requested model in both the contact and requester mail", async () => {
    for (const key of ["DATABASE_URL", "SMTP_HOST", "SMTP_USER", "SMTP_PASS", "MAIL_FROM"]) vi.stubEnv(key, "test-placeholder");
    mocks.query.mockResolvedValue({ rows: [] });
    mocks.query.mockResolvedValueOnce({ rows: [{ id: "test", name: "Taylor", email: "taylor@example.com", models: ["pplx-decider-v1-1-27b"], hardware_id: "jetson-orin-nano-super", hardware_name: "NVIDIA Jetson Orin Nano Super Developer Kit", quantity: 1, location: "office", timeline: "researching", message: "Test" }] });
    mocks.sendMail.mockResolvedValue({});
    expect(await retryHardwareInquiryMail()).toMatchObject({ sent: 1 });
    expect(mocks.sendMail).toHaveBeenCalledTimes(2);
    for (const [mail] of mocks.sendMail.mock.calls) {
      expect(mail.text).toContain("Models: pplx-decider-v1-1-27b");
      expect(mail.text).toContain("\nMachine: NVIDIA Jetson Orin Nano Super Developer Kit (jetson-orin-nano-super)");
    }
    expect(mocks.sendMail.mock.calls[1][0].text).toContain("not an order or a delivery commitment");
    expect(mocks.sendMail.mock.calls[1][0].to).toBe("taylor@example.com");
  });
  it("delivers local request subjects and selected model to both recipients without a hardware pitch", async () => {
    for (const key of ["DATABASE_URL", "SMTP_HOST", "SMTP_USER", "SMTP_PASS", "MAIL_FROM"]) vi.stubEnv(key, "test-placeholder");
    mocks.query.mockResolvedValue({ rows: [] });
    mocks.query.mockResolvedValueOnce({ rows: [{ id: "local-test", name: "Taylor", email: "taylor@example.com", models: ["h2o-lightning-31b"], request_kind: "local", quantity: 1, location: "other", timeline: "researching", message: "Linux setup help" }] });
    mocks.sendMail.mockResolvedValue({});
    expect(await retryHardwareInquiryMail()).toMatchObject({ sent: 1 });
    expect(mocks.sendMail).toHaveBeenCalledTimes(2);
    expect(mocks.sendMail.mock.calls[0][0].subject).toBe("New local model setup request");
    expect(mocks.sendMail.mock.calls[1][0].subject).toBe("We received your local setup request");
    for (const [mail] of mocks.sendMail.mock.calls) {
      expect(mail.text).toContain("Request type: Local setup");
      expect(mail.text).toContain("Models: h2o-lightning-31b");
      expect(mail.text).not.toContain("Machine:");
    }
    expect(mocks.sendMail.mock.calls[1][0].text).toContain("not an order or a promise of installer support");
  });

});
