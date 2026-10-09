CREATE TABLE IF NOT EXISTS stripe_events (
  event_id text PRIMARY KEY,
  event_type text NOT NULL,
  processed_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS licence_records (
  id bigserial PRIMARY KEY,
  key_hash char(64) NOT NULL UNIQUE,
  plan text NOT NULL DEFAULT 'commercial',
  status text NOT NULL DEFAULT 'active',
  customer_id text,
  subscription_id text,
  checkout_session_id text UNIQUE,
  company text NOT NULL,
  email text NOT NULL,
  expires_at timestamptz,
  past_due_since timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS licence_records_subscription_idx ON licence_records (subscription_id);

CREATE TABLE IF NOT EXISTS licence_deliveries (
  checkout_session_id text PRIMARY KEY,
  encrypted_key text NOT NULL,
  expires_at timestamptz NOT NULL,
  claimed_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS outbound_emails (
  id bigserial PRIMARY KEY,
  recipient text NOT NULL,
  subject text NOT NULL,
  encrypted_text text,
  reply_to text,
  attempts integer NOT NULL DEFAULT 0,
  last_error text,
  created_at timestamptz NOT NULL DEFAULT now(),
  sent_at timestamptz
);
ALTER TABLE outbound_emails ALTER COLUMN encrypted_text DROP NOT NULL;
CREATE INDEX IF NOT EXISTS outbound_emails_pending_idx ON outbound_emails (created_at) WHERE sent_at IS NULL;

CREATE TABLE IF NOT EXISTS hardware_inquiries (
  id bigserial PRIMARY KEY,
  name text NOT NULL,
  email text NOT NULL,
  company text,
  models text[] NOT NULL DEFAULT '{}',
  quantity integer NOT NULL CHECK (quantity BETWEEN 1 AND 1000),
  location text NOT NULL,
  timeline text NOT NULL,
  message text NOT NULL DEFAULT '',
  consent boolean NOT NULL CHECK (consent),
  mail_attempts integer NOT NULL DEFAULT 0,
  mail_last_error text,
  contact_mail_sent_at timestamptz,
  requester_mail_sent_at timestamptz,
  mail_sent_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS hardware_inquiries_pending_idx ON hardware_inquiries (created_at) WHERE mail_sent_at IS NULL;
