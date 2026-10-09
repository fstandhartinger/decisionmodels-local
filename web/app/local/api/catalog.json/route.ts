import { publicCatalog } from "@/lib/catalog";
import { json } from "@/lib/server/http";

export const dynamic = "force-dynamic";

export async function GET() {
  return json({ schema: "decisionmodels-local-catalog/1", models: publicCatalog() }, 200, { "Cache-Control": "public, max-age=60, stale-while-revalidate=300" });
}
