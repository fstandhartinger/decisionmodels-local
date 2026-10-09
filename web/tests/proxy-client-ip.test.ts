import { afterEach, describe, expect, it, vi } from "vitest";
import { createHmac } from "node:crypto";
import { requestIp } from "../lib/server/rate-limit";
const secret = "test-only-proxy-signing-key-at-least-32-characters";
function request(ip: string, signature?: string) {
  return new Request("https://decisionmodels.io/local/api/contact", { headers: {
    "x-forwarded-for": "198.51.100.99, 172.18.0.1", "x-dm-client-ip": ip,
    ...(signature ? { "x-dm-client-ip-signature": signature } : {})
  }});
}
function sign(ip: string, key = secret) { return createHmac("sha256", key).update("decisionmodels-client-ip-v1:" + ip, "utf8").digest("hex"); }
afterEach(() => vi.unstubAllEnvs());
describe("authenticated proxy client address", () => {
  it("accepts an authenticated IPv4 or IPv6 address through the hub", () => {
    vi.stubEnv("DM_PROXY_IP_SECRET", secret);
    for (const ip of ["203.0.113.27", "2001:db8::27"]) expect(requestIp(request(ip, sign(ip)))).toBe(ip);
  });
  it("ignores an unsigned public header and keeps the rightmost proxy-provided hop", () => {
    vi.stubEnv("DM_PROXY_IP_SECRET", secret);
    expect(requestIp(request("203.0.113.27"))).toBe("172.18.0.1");
  });
  it("rejects a changed address, wrong signature and malformed signature without throwing", () => {
    vi.stubEnv("DM_PROXY_IP_SECRET", secret);
    for (const signature of [sign("203.0.113.28"), "0".repeat(64), "short", "z".repeat(64)]) expect(requestIp(request("203.0.113.27", signature))).toBe("172.18.0.1");
  });
  it("rejects signed non-addresses and disabled or weak shared secrets", () => {
    vi.stubEnv("DM_PROXY_IP_SECRET", secret);
    expect(requestIp(request("not-an-ip", sign("not-an-ip")))).toBe("172.18.0.1");
    for (const key of ["", "weak"]) { vi.stubEnv("DM_PROXY_IP_SECRET", key); expect(requestIp(request("203.0.113.27", sign("203.0.113.27", key)))).toBe("172.18.0.1"); }
  });
});
