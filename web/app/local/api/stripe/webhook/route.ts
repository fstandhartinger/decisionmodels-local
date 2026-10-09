import Stripe from "stripe";
import { createLicenceKey, hashLicenceKey } from "@/lib/licence-core";
import { handleStripeWebhook } from "@/lib/webhook-core";
import { json, readText } from "@/lib/server/http";
import { encryptMessage, getEncryptionKeyReady, getPool, retryQueuedMail } from "@/lib/server-runtime.mjs";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

function idOf(value: string | { id: string } | null | undefined) {
  return typeof value === "string" ? value : value?.id ?? null;
}

function queueEmail(client: { query(sql: string, params?: unknown[]): Promise<unknown> }, recipient: string, subject: string, body: string, replyTo?: string) {
  return client.query("INSERT INTO outbound_emails (recipient, subject, encrypted_text, reply_to) VALUES ($1,$2,$3,$4)", [recipient, subject, encryptMessage(body), replyTo ?? null]);
}

async function processEvent(client: Parameters<Parameters<typeof handleStripeWebhook<Stripe.Event>>[0]["processEvent"]>[0], event: Stripe.Event) {
  if (event.type === "checkout.session.completed") {
    const session = event.data.object as Stripe.Checkout.Session;
    const company = session.metadata?.company?.trim();
    const email = session.customer_details?.email ?? session.customer_email;
    if (!company || !email) throw new Error("Checkout is missing company metadata or buyer email.");
    const sessionId = session.id;
    const existing = await client.query("SELECT id FROM licence_records WHERE checkout_session_id = $1", [sessionId]);
    if (existing.rows.length) return;
    const key = createLicenceKey();
    const keyHash = hashLicenceKey(key);
    const customerId = idOf(session.customer as string | { id: string } | null);
    const subscriptionId = idOf(session.subscription as string | { id: string } | null);
    const inserted = await client.query(
      "INSERT INTO licence_records (key_hash, plan, status, customer_id, subscription_id, checkout_session_id, company, email) VALUES ($1,'commercial',$2,$3,$4,$5,$6,$7) ON CONFLICT (checkout_session_id) DO NOTHING RETURNING id",
      [keyHash, session.payment_status === "unpaid" ? "pending" : "active", customerId, subscriptionId, sessionId, company, email]
    );
    if (!inserted.rows.length) return;
    await client.query("INSERT INTO licence_deliveries (checkout_session_id, encrypted_key, expires_at) VALUES ($1,$2,now() + interval '1 hour') ON CONFLICT (checkout_session_id) DO NOTHING", [sessionId, encryptMessage(key)]);
    await queueEmail(client, email, "Your Decision Models commercial licence key", `Your commercial installer licence key is:\n\n${key}\n\nActivate it with: dm-local licence activate ${key}\n\nModel licences are separate. Review each model's terms before use.`);
    await queueEmail(client, process.env.CONTACT_TO || "info@decisionmodels.io", "Commercial installer licence purchased", `Company: ${company}\nBuyer: ${email}\nCheckout session: ${sessionId}\nSubscription: ${subscriptionId ?? "not supplied"}`, email);
    return;
  }
  if (event.type === "customer.subscription.updated" || event.type === "customer.subscription.deleted") {
    const subscription = event.data.object as Stripe.Subscription & { current_period_end?: number };
    const status = event.type === "customer.subscription.deleted" ? "canceled" : subscription.status;
    const expiry = subscription.current_period_end ? new Date(subscription.current_period_end * 1000).toISOString() : null;
    await client.query("UPDATE licence_records SET status = $2, expires_at = $3, past_due_since = CASE WHEN $2 = 'past_due' THEN COALESCE(past_due_since, now()) ELSE NULL END, updated_at = now() WHERE subscription_id = $1", [subscription.id, status, expiry]);
    return;
  }
  if (event.type === "invoice.payment_failed") {
    const invoice = event.data.object as Stripe.Invoice & { subscription?: string | { id: string }; parent?: { subscription_details?: { subscription?: string | { id: string } } } };
    const subscriptionId = idOf(invoice.subscription) ?? idOf(invoice.parent?.subscription_details?.subscription);
    if (subscriptionId) await client.query("UPDATE licence_records SET status = 'past_due', past_due_since = COALESCE(past_due_since, now()), updated_at = now() WHERE subscription_id = $1", [subscriptionId]);
  }
}

export async function POST(request: Request) {
  const signature = request.headers.get("stripe-signature");
  const signingSecret = process.env.STRIPE_WEBHOOK_SECRET;
  if (!signature || !signingSecret) return json({ error: "Webhook signature configuration is missing." }, 400);
  if (!getEncryptionKeyReady()) return json({ error: "Licence delivery encryption is not configured." }, 503);
  const rawBody = await readText(request, 1_000_000);
  if (rawBody === null) return json({ error: "Webhook payload is too large or unreadable." }, 413);
  try {
    const stripe = new Stripe(process.env.STRIPE_SECRET_KEY || "sk_test_webhook_signature_only");
    const result = await handleStripeWebhook({ payload: rawBody, signature, secret: signingSecret, stripe, database: getPool(), processEvent });
    await retryQueuedMail();
    return json({ received: true, duplicate: result.duplicate });
  } catch {
    return json({ error: "Webhook signature or event processing failed." }, 400);
  }
}
