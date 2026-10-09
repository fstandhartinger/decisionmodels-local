import { createHash } from "node:crypto";

type Bucket = { count: number; resetAt: number };
const buckets = new Map<string, Bucket>();

export function checkRateLimit(key: string, limit: number, windowMs: number, now = Date.now()) {
  const current = buckets.get(key);
  if (!current || current.resetAt <= now) {
    buckets.set(key, { count: 1, resetAt: now + windowMs });
    if (buckets.size > 5000) for (const [bucketKey, bucket] of buckets) if (bucket.resetAt <= now) buckets.delete(bucketKey);
    return { allowed: true, remaining: limit - 1 };
  }
  if (current.count >= limit) return { allowed: false, remaining: 0, retryAfterSeconds: Math.ceil((current.resetAt - now) / 1000) };
  current.count += 1;
  return { allowed: true, remaining: limit - current.count };
}

export function requestIp(request: Request) {
  const forwarded = request.headers.get("x-forwarded-for");
  if (forwarded) {
    const hops = forwarded.split(",").map((hop) => hop.trim()).filter(Boolean);
    if (hops.length) return hops[hops.length - 1];
  }
  return "unknown";
}

export function checkContactRateLimit(ip: string, email: string, now = Date.now()) {
  const emailKey = createHash("sha256").update(email.trim().toLowerCase()).digest("hex");
  const limits = [
    checkRateLimit(`contact-ip:${ip}`, 5, 60 * 60 * 1000, now),
    checkRateLimit(`contact-email:${emailKey}`, 3, 24 * 60 * 60 * 1000, now)
  ];
  const blocked = limits.find((limit) => !limit.allowed);
  if (blocked) return blocked;
  const global = checkRateLimit("contact-global-daily", 150, 24 * 60 * 60 * 1000, now);
  if (!global.allowed) return global;
  return { allowed: true, remaining: Math.min(global.remaining ?? 0, ...limits.map((limit) => limit.remaining ?? 0)) };
}
