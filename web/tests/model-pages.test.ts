import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import ModelLocalPage, { generateStaticParams } from "../app/models/[slug]/local/page";
import { loadHardwareAll } from "../lib/hardware-all";
import { isInstallerSupported, loadCatalog } from "../lib/catalog";

async function render(slug: string) {
  return renderToStaticMarkup(await ModelLocalPage({ params: Promise.resolve({ slug }) }));
}

describe("model local pages", () => {
  const hardware = loadHardwareAll();
  const slugs = generateStaticParams().map((item) => item.slug);

  it("builds a page for every hardware slug and every catalogue model", () => {
    expect(hardware.length).toBeGreaterThan(0);
    for (const entry of hardware) expect(slugs).toContain(entry.slug);
    for (const model of loadCatalog()) expect(slugs).toContain(model.slug);
  });

  it("keeps supported installer pages with the licence box and hyperscaler guide", async () => {
    for (const slug of slugs) {
      const model = loadCatalog().find((item) => item.slug === slug);
      if (!isInstallerSupported(model)) continue;
      const html = await render(slug);
      expect(html, slug).toContain("Free for individuals and companies with up to 10 employees and up to USD 1M ARR.");
      expect(html, slug).toContain("USD 1,000 one-time + USD 100/month");
      expect(html, slug).toContain("Buy company licence");
      expect(html, slug).toContain("Run it on AWS, Azure or Google Cloud");
      expect(html, slug).toContain("your data never leaves your machines");
    }
  }, 60_000);

  const COMMANDS = /dm-local (?:install|plan|uninstall|remote)|curl [^<]*install\.sh|vllm serve|pip install vllm|llama-server/;
  const supported = loadCatalog().filter(isInstallerSupported);

  it("shows Local install on request, and no commands, for models without installer support", async () => {
    const catalogue = loadCatalog();
    const unsupported = [
      ...hardware.filter((entry) => !catalogue.some((model) => model.slug === entry.slug)).map((entry) => entry.slug),
      ...catalogue.filter((model) => model.installer_policy?.status !== "excluded" && !isInstallerSupported(model)).map((model) => model.slug)
    ];
    expect(unsupported.length).toBeGreaterThan(0);
    for (const slug of unsupported) {
      const html = await render(slug);
      expect(html, slug).toContain("Local install on request");
      expect(html, slug).toContain('name="request_kind" value="local"');
      expect(html, slug).toContain('type="hidden" name="models"');
      expect(html, slug).not.toContain("Buy company licence");
      expect(html, slug).not.toMatch(COMMANDS);
      expect(html, slug).not.toContain("Manual, not covered");
      expect(html, slug).toContain("Buying an installer licence does not add support for this model.");
    }
  });

  it("keeps the installer commands on supported models", async () => {
    expect(supported.length).toBeGreaterThan(0);
    for (const model of supported) {
      const html = await render(model.slug);
      expect(html, model.slug).toContain(`dm-local install ${model.slug}`);
      expect(html, model.slug).not.toContain("Local install on request");
    }
  });

  it("links benchmark badges to current model ranks without stale rank numbers", async () => {
    for (const model of supported) {
      const html = await render(model.slug);
      for (const [key, benchmark] of Object.entries(model.benchmarks ?? {})) {
        const route = key === "jevbench" ? "jev-models" : "image-jev-bench";
        expect(html).toContain(`href="${benchmark.page ?? `https://benchmarkheaven.com/${route}/${benchmark.key ?? model.slug}`}"`);
        expect(html).toContain("See the current rank on Benchmark Heaven");
      }
      expect(html).not.toMatch(/#\d+ on (?:JevBench|ImageJevBench)/);
    }
  });

  it("says hardware is on request when the data has no size", async () => {
    const unknown = hardware.find((entry) => !entry.min && !loadCatalog().some((model) => model.slug === entry.slug));
    if (!unknown) return;
    expect(await render(unknown.slug)).toContain("We first check the model reference, access to weights, model licence and your hardware.");
  });

  it("does not claim anything about hosting location or certifications", async () => {
    const html = await render(hardware[0].slug);
    expect(html).not.toMatch(/Helsinki|Finland|ISO 27001|SOC 2|certified/i);
  });

  it("shows catalogue notes without echoed badges or split units", async () => {
    for (const slug of slugs) {
      const text = (await render(slug)).replace(/<[^>]+>/g, " ").replace(/\s+/g, " ");
      expect(text, slug).not.toMatch(/\bNo No\b|\bNot yet Not yet\b/);
      expect(text, slug).not.toMatch(/\bp 50\b|\bH 100\b/);
      expect(text, slug).not.toMatch(/\bcatalog\b/);
    }
  });
});

describe("local sitemap", () => {
  it("lists /local, /hardware and every indexable model page, and none of the excluded or private routes", async () => {
    const { GET } = await import("../app/local/sitemap.xml/route");
    const response = await GET();
    expect(response.headers.get("content-type")).toContain("application/xml");
    const xml = await response.text();
    expect(xml).toContain("<loc>https://decisionmodels.io/local</loc>");
    expect(xml).toContain("<loc>https://decisionmodels.io/hardware</loc>");
    for (const model of loadCatalog()) {
      const listed = xml.includes(`<loc>https://decisionmodels.io/models/${model.slug}/local</loc>`);
      expect(listed, model.slug).toBe(model.installer_policy?.status !== "excluded");
    }
    for (const entry of loadHardwareAll()) {
      const model = loadCatalog().find((item) => item.slug === entry.slug);
      expect(xml.includes(`/models/${entry.slug}/local<`), entry.slug).toBe(model?.installer_policy?.status !== "excluded");
    }
    expect(xml).not.toMatch(/\/local\/(licence|api|install)/);
  });
});
