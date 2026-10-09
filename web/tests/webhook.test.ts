import { describe, expect, it } from "vitest";
import { handleStripeWebhook } from "../lib/webhook-core";

describe("Stripe webhook idempotency", () => {
  it("constructs the event from the raw payload and processes an event id once", async () => {
    const eventIds = new Set<string>();
    const fakeDatabase = {
      async connect() {
        return {
          async query(sql: string, params: unknown[] = []) {
            if (sql.startsWith("INSERT INTO stripe_events")) {
              const id = String(params[0]);
              if (eventIds.has(id)) return { rows: [] };
              eventIds.add(id);
              return { rows: [{ event_id: id }] };
            }
            return { rows: [] };
          },
          release() {}
        };
      }
    };
    const event = { id: "evt_test_once", type: "checkout.session.completed" };
    const calls: string[] = [];
    const stripe = { webhooks: { constructEvent: (payload: string | Buffer, signature: string, secret: string) => { expect(payload).toBe("signed raw body"); expect(signature).toBe("sig"); expect(secret).toBe("whsec_test"); return event; } } };
    const processEvent = async (_client: unknown, value: typeof event) => { calls.push(value.id); };
    const first = await handleStripeWebhook({ payload: "signed raw body", signature: "sig", secret: "whsec_test", stripe, database: fakeDatabase, processEvent });
    const second = await handleStripeWebhook({ payload: "signed raw body", signature: "sig", secret: "whsec_test", stripe, database: fakeDatabase, processEvent });
    expect(first.duplicate).toBe(false);
    expect(second.duplicate).toBe(true);
    expect(calls).toEqual(["evt_test_once"]);
  });
});
