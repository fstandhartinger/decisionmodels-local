import { json } from "@/lib/server/http";
import { databaseReady, getPool } from "@/lib/server-runtime.mjs";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET() {
  let database: "ready" | "not_configured" | "unavailable" = "not_configured";
  if (databaseReady()) {
    try { await getPool().query("SELECT 1"); database = "ready"; }
    catch { database = "unavailable"; }
  }
  return json({ status: database === "unavailable" ? "degraded" : "ok", database, timestamp: new Date().toISOString() }, database === "unavailable" ? 503 : 200);
}
