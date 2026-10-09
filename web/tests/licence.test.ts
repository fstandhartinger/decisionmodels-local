import { describe, expect, it } from "vitest";
import { constantTimeHashMatch, createLicenceKey, hashLicenceKey, licenceIsActive, validLicenceKeyFormat } from "../lib/licence-core";

describe("licence keys", () => {
  it("creates a 32-character base32 suffix and stores only its hash", () => {
    const key = createLicenceKey(() => Buffer.alloc(20, 0xff));
    expect(key).toMatch(/^dmlk_[A-Z2-7]{32}$/);
    expect(validLicenceKeyFormat(key)).toBe(true);
    expect(hashLicenceKey(key)).toHaveLength(64);
    expect(constantTimeHashMatch(hashLicenceKey(key), hashLicenceKey(key))).toBe(true);
    expect(constantTimeHashMatch(hashLicenceKey(key), hashLicenceKey("dmlk_AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"))).toBe(false);
  });

  it("accepts active and less-than-14-day past-due subscriptions", () => {
    const now = Date.UTC(2026, 9, 9);
    expect(licenceIsActive("active", null, now)).toBe(true);
    expect(licenceIsActive("active", null, now, new Date(now - 1))).toBe(false);
    expect(licenceIsActive("active", null, now, new Date(now + 86400_000))).toBe(true);
    expect(licenceIsActive("past_due", new Date(now - 13 * 86400_000), now)).toBe(true);
    expect(licenceIsActive("past_due", new Date(now - 14 * 86400_000), now)).toBe(false);
    expect(licenceIsActive("canceled", null, now)).toBe(false);
  });
});
