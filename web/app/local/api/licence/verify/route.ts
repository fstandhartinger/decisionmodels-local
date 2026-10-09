import { constantTimeHashMatch, hashLicenceKey, licenceIsActive, validLicenceKeyFormat } from "@/lib/licence-core";
import { json, readJson } from "@/lib/server/http";
import { checkRateLimit, requestIp } from "@/lib/server/rate-limit";
import { getPool } from "@/lib/server-runtime.mjs";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function POST(request: Request) {
  const rate = checkRateLimit(`licence-verify:${requestIp(request)}`, 20, 60 * 1000);
  if (!rate.allowed) return json({ error: "Too many verification requests." }, 429, { "Retry-After": String(rate.retryAfterSeconds) });
  const body = await readJson(request, 2_000);
  const key = typeof body?.key === "string" ? body.key.trim().toUpperCase() : "";
  if (!validLicenceKeyFormat(key)) return json({ valid: false, plan: "commercial", status: "invalid", expires_at: null });
  try {
    const candidateHash = hashLicenceKey(key);
    const result = await getPool().query("SELECT key_hash, plan, status, expires_at, past_due_since FROM licence_records WHERE key_hash = $1 LIMIT 1", [candidateHash]);
    const record = result.rows[0];
    const matched = Boolean(record && constantTimeHashMatch(candidateHash, String(record.key_hash).trim()));
    const valid = matched && licenceIsActive(String(record.status), record.past_due_since as Date | string | null);
    return json({ valid, plan: "commercial", status: matched ? String(record.status) : "invalid", expires_at: matched && record.expires_at ? new Date(record.expires_at as string).toISOString() : null });
  } catch {
    return json({ error: "Licence verification is temporarily unavailable." }, 503);
  }
}
