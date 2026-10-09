import { loadCatalog } from "@/lib/catalog";
import { validateHardwareInquiry } from "@/lib/contact-validation";
import { json, readJson } from "@/lib/server/http";
import { requestIp, checkContactRateLimit } from "@/lib/server/rate-limit";
import { getPool, retryHardwareInquiryMail } from "@/lib/server-runtime.mjs";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function POST(request: Request) {
  const ip = requestIp(request);
  const body = await readJson(request, 12_000);
  if (!body) return json({ error: "The request must be valid JSON under 12 KB." }, 400);
  const models = new Set(loadCatalog().map((model) => model.slug));
  const result = validateHardwareInquiry(body, models);
  if (!result.ok) return json({ error: result.error }, 400);
  if (result.honeypot) return json({ ok: true, mail: "queued" });
  const limit = checkContactRateLimit(ip, result.value.email);
  if (!limit.allowed) return json({ error: "Please wait before sending another request." }, 429, { "Retry-After": String(limit.retryAfterSeconds) });
  try {
    const inquiry = result.value;
    const inserted = await getPool().query(
      "INSERT INTO hardware_inquiries (name, email, company, models, quantity, location, timeline, message, consent) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,true) RETURNING id",
      [inquiry.name, inquiry.email, inquiry.company, inquiry.models, inquiry.quantity, inquiry.location, inquiry.timeline, inquiry.message]
    );
    await retryHardwareInquiryMail();
    const status = await getPool().query("SELECT mail_sent_at FROM hardware_inquiries WHERE id = $1", [inserted.rows[0].id]);
    return json({ ok: true, mail: status.rows[0]?.mail_sent_at ? "sent" : "queued" });
  } catch {
    return json({ error: "The request could not be saved. Please try again later." }, 503);
  }
}
