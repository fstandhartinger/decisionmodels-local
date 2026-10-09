import { decryptMessage, getPool } from "@/lib/server-runtime.mjs";
import { json } from "@/lib/server/http";
import { checkRateLimit, requestIp } from "@/lib/server/rate-limit";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET(request: Request) {
  const rate = checkRateLimit(`licence-delivery:${requestIp(request)}`, 10, 60 * 1000);
  if (!rate.allowed) return json({ error: "Too many licence delivery requests." }, 429, { "Retry-After": String(rate.retryAfterSeconds) });
  const sessionId = new URL(request.url).searchParams.get("session_id") ?? "";
  if (!/^cs_(test|live)_[A-Za-z0-9]+$/.test(sessionId)) return json({ error: "Invalid checkout reference." }, 400);
  try {
    const database = getPool();
    const client = await database.connect();
    try {
      await client.query("BEGIN");
      const claimed = await client.query("SELECT encrypted_key FROM licence_deliveries WHERE checkout_session_id = $1 AND claimed_at IS NULL AND expires_at > now() FOR UPDATE", [sessionId]);
      if (!claimed.rows.length) {
        await client.query("ROLLBACK");
        const existing = await database.query("SELECT claimed_at, expires_at FROM licence_deliveries WHERE checkout_session_id = $1", [sessionId]);
        if (existing.rows[0]?.claimed_at) return json({ error: "already_claimed" }, 410);
        if (existing.rows.length) return json({ error: "expired_or_unavailable" }, 410);
        return json({ pending: true }, 202, { "Retry-After": "2", "Cache-Control": "no-store" });
      }
      const key = decryptMessage(String(claimed.rows[0].encrypted_key));
      await client.query("UPDATE licence_deliveries SET claimed_at = now(), encrypted_key = 'consumed' WHERE checkout_session_id = $1", [sessionId]);
      await client.query("COMMIT");
      return json({ key });
    } catch (error) {
      await client.query("ROLLBACK");
      throw error;
    } finally { client.release(); }
  } catch {
    return json({ error: "Licence delivery is temporarily unavailable." }, 503);
  }
}
