import Stripe from "stripe";
import { json, readJson } from "@/lib/server/http";
import { getPool } from "@/lib/server-runtime.mjs";
import { checkRateLimit, requestIp } from "@/lib/server/rate-limit";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function POST(request: Request) {
  const rate = checkRateLimit(`portal:${requestIp(request)}`, 10, 60 * 1000);
  if (!rate.allowed) return json({ error: "Please wait before opening the billing portal again." }, 429, { "Retry-After": String(rate.retryAfterSeconds) });
  const body = await readJson(request, 4_000);
  const sessionId = typeof body?.session_id === "string" ? body.session_id : "";
  if (!/^cs_(test|live)_[A-Za-z0-9]+$/.test(sessionId)) return json({ error: "A valid checkout session reference is required." }, 400);
  if (!process.env.STRIPE_SECRET_KEY) return json({ error: "The billing portal is not configured." }, 503);
  try {
    const result = await getPool().query("SELECT customer_id, status, created_at FROM licence_records WHERE checkout_session_id = $1", [sessionId]);
    const status = result.rows[0]?.status;
    if (status === "pending" || status === "payment_failed") return json({ error: "payment_pending" }, 409);
    const createdAt = result.rows[0]?.created_at ? new Date(result.rows[0].created_at as string | Date).getTime() : 0;
    if (!createdAt || Date.now() - createdAt > 60 * 60 * 1000) return json({ error: "portal_link_expired" }, 410);
    const customer = result.rows[0]?.customer_id;
    if (typeof customer !== "string" || !customer) return json({ error: "No customer account is associated with this checkout." }, 404);
    const stripe = new Stripe(process.env.STRIPE_SECRET_KEY);
    const portal = await stripe.billingPortal.sessions.create({ customer, return_url: "https://decisionmodels.io/local/licence/success?session_id=" + encodeURIComponent(sessionId) });
    return json({ url: portal.url });
  } catch {
    return json({ error: "The billing portal could not be opened." }, 502);
  }
}
