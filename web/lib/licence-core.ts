import { createHash, randomBytes, timingSafeEqual } from "node:crypto";

const BASE32 = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567";

export function createLicenceKey(random = randomBytes) {
  const bytes = random(20);
  let buffer = 0;
  let bits = 0;
  let output = "";
  for (const byte of bytes) {
    buffer = (buffer << 8) | byte;
    bits += 8;
    while (bits >= 5 && output.length < 32) {
      bits -= 5;
      output += BASE32[(buffer >> bits) & 31];
    }
  }
  return `dmlk_${output}`;
}

export function hashLicenceKey(key: string) {
  return createHash("sha256").update(key, "utf8").digest("hex");
}

export function validLicenceKeyFormat(key: string) {
  return /^dmlk_[A-Z2-7]{32}$/.test(key);
}

export function constantTimeHashMatch(candidate: string, stored: string) {
  if (!/^[a-f0-9]{64}$/i.test(candidate) || !/^[a-f0-9]{64}$/i.test(stored)) return false;
  return timingSafeEqual(Buffer.from(candidate, "hex"), Buffer.from(stored, "hex"));
}

export function licenceIsActive(status: string, pastDueSince: Date | string | null, now = Date.now()) {
  if (status === "active") return true;
  if (status !== "past_due" || !pastDueSince) return false;
  const start = pastDueSince instanceof Date ? pastDueSince.getTime() : Date.parse(pastDueSince);
  return Number.isFinite(start) && now - start < 14 * 24 * 60 * 60 * 1000;
}
