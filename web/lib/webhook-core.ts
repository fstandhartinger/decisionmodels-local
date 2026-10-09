export type WebhookDatabase = { connect(): Promise<{ query(sql: string, params?: unknown[]): Promise<{ rows: unknown[] }>; release(): void }> };
export type StripeLike = { webhooks: { constructEvent(payload: string | Buffer, signature: string, secret: string): unknown } };

export async function handleStripeWebhook<T>({ payload, signature, secret, stripe, database, processEvent }: {
  payload: string | Buffer;
  signature: string;
  secret: string;
  stripe: StripeLike;
  database: WebhookDatabase;
  processEvent: (client: Awaited<ReturnType<WebhookDatabase["connect"]>>, event: T) => Promise<void>;
}) {
  const event = stripe.webhooks.constructEvent(payload, signature, secret) as T;
  const eventRecord = event as { id?: string; type?: string };
  if (!eventRecord.id || !eventRecord.type) throw new Error("Invalid Stripe event.");
  const client = await database.connect();
  try {
    await client.query("BEGIN");
    const inserted = await client.query("INSERT INTO stripe_events (event_id, event_type) VALUES ($1, $2) ON CONFLICT (event_id) DO NOTHING RETURNING event_id", [eventRecord.id, eventRecord.type]);
    if (!inserted.rows.length) {
      await client.query("ROLLBACK");
      return { event, duplicate: true };
    }
    await processEvent(client, event);
    await client.query("COMMIT");
    return { event, duplicate: false };
  } catch (error) {
    await client.query("ROLLBACK");
    throw error;
  } finally {
    client.release();
  }
}
