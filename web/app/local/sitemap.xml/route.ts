import { loadCatalog } from "@/lib/catalog";
import { loadHardwareAll } from "@/lib/hardware-all";

export const dynamic = "force-dynamic";

const ORIGIN = "https://decisionmodels.io";

/** Indexable local pages only: excluded models keep their robots noindex and stay out; licence, checkout and API routes are not listed. */
function sitemapPaths(): string[] {
  const excluded = new Set(loadCatalog().filter((model) => model.installer_policy?.status === "excluded").map((model) => model.slug));
  const slugs = new Set([...loadCatalog().map((model) => model.slug), ...loadHardwareAll().map((entry) => entry.slug)]);
  for (const slug of excluded) slugs.delete(slug);
  return ["/local", "/hardware", ...[...slugs].sort().map((slug) => `/models/${slug}/local`)];
}

export async function GET() {
  const body = `<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n${sitemapPaths().map((path) => `<url><loc>${ORIGIN}${path}</loc></url>\n`).join("")}</urlset>\n`;
  return new Response(body, { headers: { "Content-Type": "application/xml; charset=utf-8", "Cache-Control": "public, max-age=3600" } });
}
