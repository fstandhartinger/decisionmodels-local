import { afterEach, describe, expect, it } from "vitest";
import type Stripe from "stripe";
import { processStripeEvent as processEvent } from "@/lib/stripe-event";

type QueryCall = { sql: string; params: unknown[] };
function fakeClient(existing?: { id: number; status: string }) {
  const calls: QueryCall[] = [];
  return {
    calls,
    async query(sql: string, params: unknown[] = []) {
      calls.push({ sql, params });
      if (sql.startsWith("SELECT id, status FROM licence_records")) return { rows: existing ? [existing] : [] };
      if (sql.startsWith("INSERT INTO licence_records") && sql.includes("RETURNING id")) return { rows: [{ id: 1 }] };
      return { rows: [] };
    },
    release() {}
  };
}

function stripeEvent(type: string, object: unknown): Stripe.Event {
  return { id: `evt_${type}`, type, data: { object } } as unknown as Stripe.Event;
}

const originalSecret = process.env.LICENCE_DELIVERY_SECRET;
afterEach(() => {
  if (originalSecret === undefined) delete process.env.LICENCE_DELIVERY_SECRET;
  else process.env.LICENCE_DELIVERY_SECRET = originalSecret;
});

describe("paid-only licence delivery", () => {
  const session = {
    id: "cs_test_delayed_123",
    metadata: { company: "Example Ltd", purpose: "decisionmodels_local_commercial" },
    customer_details: { email: "buyer@example.com" },
    customer_email: null,
    customer: "cus_123",
    subscription: "sub_123",
    payment_status: "unpaid"
  };

  it("ignores paid checkout events for another product in the shared Stripe account", async () => {
    const client = fakeClient();
    await processEvent(client, stripeEvent("checkout.session.completed", { ...session, payment_status: "paid", metadata: { company: "Other product buyer" } }));
    expect(client.calls).toHaveLength(0);
  });

  it("records an unpaid completed checkout as pending without creating or emailing a key", async () => {
    const client = fakeClient();
    await processEvent(client, stripeEvent("checkout.session.completed", session));

    expect(client.calls.find((call) => call.sql.startsWith("INSERT INTO licence_records"))?.params[1]).toBe("pending");
    expect(client.calls.some((call) => call.sql.startsWith("INSERT INTO licence_deliveries"))).toBe(false);
    expect(client.calls.some((call) => call.sql.startsWith("INSERT INTO outbound_emails"))).toBe(false);
  });

  it("issues and queues a key only after asynchronous payment succeeds", async () => {
    process.env.LICENCE_DELIVERY_SECRET = "test-only-encryption-secret-for-webhook";
    const client = fakeClient({ id: 1, status: "pending" });
    await processEvent(client, stripeEvent("checkout.session.async_payment_succeeded", { ...session, payment_status: "paid" }));

    expect(client.calls[0].sql).toContain("pg_advisory_xact_lock");
    expect(client.calls.some((call) => call.sql.includes("SET key_hash = $2, status = 'active'"))).toBe(true);
    expect(client.calls.some((call) => call.sql.includes("created_at = now()"))).toBe(true);
    expect(client.calls.some((call) => call.sql.startsWith("INSERT INTO licence_deliveries"))).toBe(true);
    expect(client.calls.filter((call) => call.sql.startsWith("INSERT INTO outbound_emails"))).toHaveLength(2);
  });

  it("marks failed delayed payments unusable and lets a paid invoice restore an active subscription", async () => {
    const failed = fakeClient({ id: 1, status: "pending" });
    await processEvent(failed, stripeEvent("checkout.session.async_payment_failed", session));
    expect(failed.calls.some((call) => call.sql.includes("SET status = 'payment_failed'"))).toBe(true);
    expect(failed.calls.some((call) => call.sql.startsWith("INSERT INTO licence_deliveries"))).toBe(false);

    const renewed = fakeClient();
    await processEvent(renewed, stripeEvent("invoice.paid", { subscription: "sub_123", period_end: 1_800_000_000 }));
    expect(renewed.calls.some((call) => call.sql.includes("SET status = 'active', past_due_since = NULL"))).toBe(true);
  });
});
