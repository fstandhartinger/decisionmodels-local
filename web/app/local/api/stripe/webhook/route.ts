import Stripe from "stripe";
import { handleStripeWebhook } from "@/lib/webhook-core";
import { processStripeEvent } from "@/lib/stripe-event";
import { json, readText } from "@/lib/server/http";
import { getEncryptionKeyReady, getPool, retryQueuedMail } from "@/lib/server-runtime.mjs";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function POST(request: Request) {
  const signature = request.headers.get("stripe-signature");
  const signingSecret = process.env.STRIPE_WEBHOOK_SECRET;
  if (!signature || !signingSecret) return json({ error: "Webhook signature configuration is missing." }, 400);
  if (!getEncryptionKeyReady()) return json({ error: "Licence delivery encryption is not configured." }, 503);
  const rawBody = await readText(request, 1_000_000);
  if (rawBody === null) return json({ error: "Webhook payload is too large or unreadable." }, 413);
  const stripe = new Stripe(process.env.STRIPE_SECRET_KEY || "sk_test_webhook_signature_only");
  try { stripe.webhooks.constructEvent(rawBody, signature, signingSecret); }
  catch { return json({ error: "Webhook signature verification failed." }, 400); }
  try {
    const result = await handleStripeWebhook({ payload: rawBody, signature, secret: signingSecret, stripe, database: getPool(), processEvent: processStripeEvent });
    await retryQueuedMail();
    return json({ received: true, duplicate: result.duplicate });
  } catch {
    console.error("Stripe webhook event processing failed.");
    return json({ error: "Webhook event processing failed." }, 500);
  }
}
