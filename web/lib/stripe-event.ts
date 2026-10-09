import type Stripe from "stripe";
import { createLicenceKey, hashLicenceKey } from "@/lib/licence-core";
import { encryptMessage } from "@/lib/server-runtime.mjs";
import type { WebhookDatabase } from "@/lib/webhook-core";

type EventClient = Awaited<ReturnType<WebhookDatabase["connect"]>>;

function idOf(value: string | { id: string } | null | undefined) {
  return typeof value === "string" ? value : value?.id ?? null;
}

function queueEmail(client: EventClient, recipient: string, subject: string, body: string, replyTo?: string) {
  return client.query("INSERT INTO outbound_emails (recipient, subject, encrypted_text, reply_to) VALUES ($1,$2,$3,$4)", [recipient, subject, encryptMessage(body), replyTo ?? null]);
}

async function processCheckoutSession(client: EventClient, session: Stripe.Checkout.Session, paid: boolean, failed = false) {
  if (session.metadata?.purpose !== "decisionmodels_local_commercial") return;
  const company = session.metadata?.company?.trim();
  const email = session.customer_details?.email ?? session.customer_email;
  if (!company || !email) throw new Error("Checkout is missing company metadata or buyer email.");
  const sessionId = session.id;
  // Different Stripe event IDs for one Checkout Session can arrive concurrently.
  // Serialize them so an unpaid placeholder cannot win an insert race against payment success.
  await client.query("SELECT pg_advisory_xact_lock(hashtextextended($1, 0))", [sessionId]);
  const existing = await client.query("SELECT id, status FROM licence_records WHERE checkout_session_id = $1 FOR UPDATE", [sessionId]);
  const existingStatus = (existing.rows[0] as { status?: string } | undefined)?.status;
  const customerId = idOf(session.customer as string | { id: string } | null);
  const subscriptionId = idOf(session.subscription as string | { id: string } | null);
  if (!paid) {
    if (existing.rows.length) {
      if (failed && existingStatus === "pending") await client.query("UPDATE licence_records SET status = 'payment_failed', updated_at = now() WHERE checkout_session_id = $1", [sessionId]);
      return;
    }
    await client.query(
      "INSERT INTO licence_records (key_hash, plan, status, customer_id, subscription_id, checkout_session_id, company, email) VALUES ($1,'commercial',$2,$3,$4,$5,$6,$7) ON CONFLICT (checkout_session_id) DO NOTHING",
      [hashLicenceKey(createLicenceKey()), failed ? "payment_failed" : "pending", customerId, subscriptionId, sessionId, company, email]
    );
    return;
  }
  if (existingStatus === "active") return;
  const key = createLicenceKey();
  const keyHash = hashLicenceKey(key);
  if (existing.rows.length) {
    await client.query("UPDATE licence_records SET key_hash = $2, status = 'active', customer_id = $3, subscription_id = $4, past_due_since = NULL, created_at = now(), updated_at = now() WHERE checkout_session_id = $1", [sessionId, keyHash, customerId, subscriptionId]);
  } else {
    const inserted = await client.query(
      "INSERT INTO licence_records (key_hash, plan, status, customer_id, subscription_id, checkout_session_id, company, email) VALUES ($1,'commercial','active',$2,$3,$4,$5,$6) ON CONFLICT (checkout_session_id) DO NOTHING RETURNING id",
      [keyHash, customerId, subscriptionId, sessionId, company, email]
    );
    if (!inserted.rows.length) return;
  }
  await client.query("INSERT INTO licence_deliveries (checkout_session_id, encrypted_key, expires_at) VALUES ($1,$2,now() + interval '1 hour') ON CONFLICT (checkout_session_id) DO NOTHING", [sessionId, encryptMessage(key)]);
  await queueEmail(client, email, "Your Decision Models commercial licence key", `Your commercial installer licence key is:\n\n${key}\n\nActivate it with: dm-local licence activate ${key}\n\nModel licences are separate. Review each model's terms before use.`);
  await queueEmail(client, process.env.CONTACT_TO || "info@decisionmodels.io", "Commercial installer licence purchased", `Company: ${company}\nBuyer: ${email}\nCheckout session: ${sessionId}\nSubscription: ${subscriptionId ?? "not supplied"}`, email);
}

export async function processStripeEvent(client: EventClient, event: Stripe.Event) {
  if (event.type === "checkout.session.completed") {
    const session = event.data.object as Stripe.Checkout.Session;
    await processCheckoutSession(client, session, session.payment_status === "paid");
    return;
  }
  if (event.type === "checkout.session.async_payment_succeeded") {
    await processCheckoutSession(client, event.data.object as Stripe.Checkout.Session, true);
    return;
  }
  if (event.type === "checkout.session.async_payment_failed") {
    await processCheckoutSession(client, event.data.object as Stripe.Checkout.Session, false, true);
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
    return;
  }
  if (event.type === "invoice.paid") {
    const invoice = event.data.object as Stripe.Invoice & { subscription?: string | { id: string }; parent?: { subscription_details?: { subscription?: string | { id: string } } }; period_end?: number; lines?: { data?: Array<{ period?: { end?: number } }> } };
    const subscriptionId = idOf(invoice.subscription) ?? idOf(invoice.parent?.subscription_details?.subscription);
    const periodEnd = invoice.period_end ?? invoice.lines?.data?.[0]?.period?.end;
    if (subscriptionId) await client.query("UPDATE licence_records SET status = 'active', past_due_since = NULL, expires_at = COALESCE($2, expires_at), updated_at = now() WHERE subscription_id = $1 AND status IN ('active','past_due')", [subscriptionId, periodEnd ? new Date(periodEnd * 1000).toISOString() : null]);
  }
}
