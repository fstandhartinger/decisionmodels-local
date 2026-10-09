import { describe, expect, it } from "vitest";
import { checkContactRateLimit, requestIp } from "@/lib/server/rate-limit";

describe("contact request limits", () => {
  it("uses the proxy-appended final forwarding hop", () => {
    expect(requestIp(new Request("https://decisionmodels.io", { headers: { "x-forwarded-for": "198.51.100.44, 10.0.0.9" } }))).toBe("10.0.0.9");
    expect(requestIp(new Request("https://decisionmodels.io", { headers: { "x-real-ip": "198.51.100.44" } }))).toBe("unknown");
  });

  it("limits requests by email and by an app-wide daily ceiling", () => {
    const now = 1_800_000_000_000;
    for (let attempt = 0; attempt < 3; attempt += 1) checkContactRateLimit(`email-ip-${attempt}`, "one@example.test", now);
    expect(checkContactRateLimit("email-ip-last", "ONE@example.test", now).allowed).toBe(false);

    let last = { allowed: true } as { allowed: boolean };
    for (let attempt = 0; attempt < 151; attempt += 1) last = checkContactRateLimit(`daily-ip-${attempt}`, `daily-${attempt}@example.test`, now);
    expect(last.allowed).toBe(false);
  });

  it("does not let requests rejected by the per-IP cap consume global daily capacity", () => {
    const now = 1_800_123_456_000;
    for (let attempt = 0; attempt < 200; attempt += 1) {
      checkContactRateLimit("one-noisy-ip", `noise-${attempt}@example.test`, now);
    }
    for (let attempt = 0; attempt < 145; attempt += 1) {
      expect(checkContactRateLimit(`other-ip-${attempt}`, `other-${attempt}@example.test`, now).allowed).toBe(true);
    }
    expect(checkContactRateLimit("last-ip", "last@example.test", now).allowed).toBe(false);
  });
});
