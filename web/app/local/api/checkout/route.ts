import Stripe from "stripe";
import { json, readJson } from "@/lib/server/http";
import { checkRateLimit, requestIp } from "@/lib/server/rate-limit";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function POST(request: Request) {
  const rate = checkRateLimit(`checkout:${requestIp(request)}`, 5, 60 * 1000);
  if (!rate.allowed) return json({ error: "Please wait before starting another checkout." }, 429, { "Retry-After": String(rate.retryAfterSeconds) });
  const body = await readJson(request, 8_000);
  if (!body) return json({ error: "The request must be valid JSON." }, 400);
  const company = typeof body.company === "string" ? body.company.trim() : "";
  const email = typeof body.email === "string" ? body.email.trim() : "";
  if (company.length < 2 || company.length > 160) return json({ error: "Enter a company name between 2 and 160 characters." }, 400);
  if (email.length > 254 || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) return json({ error: "Enter a valid email address." }, 400);
  if (body.declaration !== true) return json({ error: "The commercial company-size declaration is required." }, 400);
  if (body.terms !== true) return json({ error: "Accept the commercial licence terms to continue." }, 400);
  const stripeSecret = process.env.STRIPE_SECRET_KEY;
  const setupPrice = process.env.STRIPE_PRICE_SETUP;
  const monthlyPrice = process.env.STRIPE_PRICE_MONTHLY;
  if (!stripeSecret || !setupPrice || !monthlyPrice) return json({ error: "Commercial checkout is not configured yet. Please contact info@decisionmodels.io." }, 503);
  try {
    const stripe = new Stripe(stripeSecret);
    const params: Stripe.Checkout.SessionCreateParams = {
      mode: "subscription",
      line_items: [{ price: setupPrice, quantity: 1 }, { price: monthlyPrice, quantity: 1 }],
      automatic_tax: { enabled: true },
      tax_id_collection: { enabled: true },
      billing_address_collection: "required",
      // Subscription-mode Checkout creates the customer automatically when none is supplied.
      customer_email: email,
      success_url: "https://decisionmodels.io/local/licence/success?session_id={CHECKOUT_SESSION_ID}",
      cancel_url: "https://decisionmodels.io/local/licence?checkout=cancelled",
      metadata: { company, declaration: "true", purpose: "decisionmodels_local_commercial" },
      subscription_data: { metadata: { company, declaration: "true", purpose: "decisionmodels_local_commercial" } }
    };
    const session = await stripe.checkout.sessions.create(params);
    if (!session.url) return json({ error: "Stripe did not return a checkout URL." }, 502);
    return json({ url: session.url });
  } catch {
    return json({ error: "Stripe checkout could not be created. Please try again later." }, 502);
  }
}
