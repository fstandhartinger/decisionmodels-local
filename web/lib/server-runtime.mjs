import crypto from "node:crypto";
import fs from "node:fs/promises";
import path from "node:path";
import pg from "pg";
import nodemailer from "nodemailer";

const { Pool } = pg;
let pool;
export function getPool() {
  if (!process.env.DATABASE_URL) throw new Error("DATABASE_URL is not configured.");
  if (!pool) pool = new Pool({ connectionString: process.env.DATABASE_URL, max: 10, idleTimeoutMillis: 30000 });
  return pool;
}

function encryptionKey() {
  const secret = process.env.LICENCE_DELIVERY_SECRET;
  if (!secret || secret.length < 32) throw new Error("LICENCE_DELIVERY_SECRET must contain at least 32 characters.");
  return crypto.createHash("sha256").update(secret, "utf8").digest();
}

export function encryptMessage(value) {
  const iv = crypto.randomBytes(12);
  const cipher = crypto.createCipheriv("aes-256-gcm", encryptionKey(), iv);
  const ciphertext = Buffer.concat([cipher.update(value, "utf8"), cipher.final()]);
  return [iv.toString("base64url"), cipher.getAuthTag().toString("base64url"), ciphertext.toString("base64url")].join(".");
}

export function decryptMessage(value) {
  const [ivPart, tagPart, bodyPart] = value.split(".");
  if (!ivPart || !tagPart || !bodyPart) throw new Error("Invalid encrypted message.");
  const decipher = crypto.createDecipheriv("aes-256-gcm", encryptionKey(), Buffer.from(ivPart, "base64url"));
  decipher.setAuthTag(Buffer.from(tagPart, "base64url"));
  return Buffer.concat([decipher.update(Buffer.from(bodyPart, "base64url")), decipher.final()]).toString("utf8");
}

export function createMailer() {
  const host = process.env.SMTP_HOST;
  const user = process.env.SMTP_USER;
  const pass = process.env.SMTP_PASS;
  if (!host || !user || !pass || !process.env.MAIL_FROM) return null;
  const port = Number(process.env.SMTP_PORT || 587);
  return nodemailer.createTransport({ host, port, secure: port === 465, auth: { user, pass } });
}

export async function sendPlainEmail({ to, subject, text, replyTo }) {
  const transporter = createMailer();
  if (!transporter) return false;
  await transporter.sendMail({ from: process.env.MAIL_FROM, to, subject, text, ...(replyTo ? { replyTo } : {}) });
  return true;
}

export async function runMigrations() {
  if (!process.env.DATABASE_URL) return { skipped: true };
  const directory = path.join(process.cwd(), "migrations");
  const files = (await fs.readdir(directory)).filter((name) => name.endsWith(".sql")).sort();
  const client = await getPool().connect();
  try {
    for (const file of files) await client.query(await fs.readFile(path.join(directory, file), "utf8"));
    await client.query("DELETE FROM licence_deliveries WHERE expires_at <= now() OR claimed_at < now() - interval '1 day'");
  } finally { client.release(); }
  return { skipped: false, migrations: files.length };
}

async function recordMailResult(poolRef, id, error) {
  if (error) await poolRef.query("UPDATE outbound_emails SET attempts = attempts + 1, last_error = $2 WHERE id = $1", [id, String(error).slice(0, 500)]);
  else await poolRef.query("UPDATE outbound_emails SET attempts = attempts + 1, sent_at = now(), last_error = NULL WHERE id = $1", [id]);
}

export async function retryQueuedMail() {
  if (!process.env.DATABASE_URL) return { skipped: true };
  const poolRef = getPool();
  const pending = await poolRef.query("SELECT id, recipient, subject, encrypted_text, reply_to FROM outbound_emails WHERE sent_at IS NULL ORDER BY id LIMIT 50");
  let sent = 0;
  for (const row of pending.rows) {
    try {
      const text = decryptMessage(row.encrypted_text);
      const ok = await sendPlainEmail({ to: row.recipient, subject: row.subject, text, replyTo: row.reply_to ?? undefined });
      if (!ok) { await recordMailResult(poolRef, row.id, "SMTP is not configured."); continue; }
      await poolRef.query("UPDATE outbound_emails SET attempts = attempts + 1, sent_at = now(), encrypted_text = NULL, last_error = NULL WHERE id = $1", [row.id]);
      sent += 1;
    } catch (error) { await recordMailResult(poolRef, row.id, error); }
  }
  return { sent, pending: pending.rows.length };
}

export async function retryHardwareInquiryMail() {
  if (!process.env.DATABASE_URL) return { skipped: true };
  const poolRef = getPool();
  const pending = await poolRef.query("SELECT id, name, email, company, models, quantity, location, timeline, message, contact_mail_sent_at, requester_mail_sent_at FROM hardware_inquiries WHERE mail_sent_at IS NULL ORDER BY created_at LIMIT 25");
  let sent = 0;
  for (const row of pending.rows) {
    try {
      const details = `Name: ${row.name}\nEmail: ${row.email}\nCompany: ${row.company ?? "—"}\nModels: ${(row.models ?? []).join(", ")}\nQuantity: ${row.quantity}\nWhere: ${row.location}\nTimeline: ${row.timeline}\n\n${row.message}`;
      let contactSent = Boolean(row.contact_mail_sent_at);
      let requesterSent = Boolean(row.requester_mail_sent_at);
      if (!contactSent) {
        contactSent = await sendPlainEmail({ to: process.env.CONTACT_TO || "info@decisionmodels.io", subject: "New pre-installed hardware request", text: details, replyTo: row.email });
        if (contactSent) await poolRef.query("UPDATE hardware_inquiries SET contact_mail_sent_at = now() WHERE id = $1", [row.id]);
      }
      if (!requesterSent) {
        requesterSent = await sendPlainEmail({ to: row.email, subject: "We received your hardware request", text: "Thank you for contacting Decision Models. We have received your hardware request and will reply after checking the configuration." });
        if (requesterSent) await poolRef.query("UPDATE hardware_inquiries SET requester_mail_sent_at = now() WHERE id = $1", [row.id]);
      }
      if (contactSent && requesterSent) {
        await poolRef.query("UPDATE hardware_inquiries SET mail_attempts = mail_attempts + 1, mail_sent_at = now(), mail_last_error = NULL WHERE id = $1", [row.id]);
        sent += 1;
      } else {
        await poolRef.query("UPDATE hardware_inquiries SET mail_attempts = mail_attempts + 1, mail_last_error = 'SMTP is unavailable.' WHERE id = $1", [row.id]);
      }
    } catch (error) {
      await poolRef.query("UPDATE hardware_inquiries SET mail_attempts = mail_attempts + 1, mail_last_error = $2 WHERE id = $1", [row.id, String(error).slice(0, 500)]);
    }
  }
  return { sent, pending: pending.rows.length };
}

export async function retryAllQueuedMail() {
  const [licence, hardware] = await Promise.all([retryQueuedMail(), retryHardwareInquiryMail()]);
  return { licence, hardware };
}

export function databaseReady() {
  return Boolean(process.env.DATABASE_URL);
}

export function getEncryptionKeyReady() {
  try { encryptionKey(); return true; } catch { return false; }
}
