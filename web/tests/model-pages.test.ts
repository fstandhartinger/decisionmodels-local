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

  it("renders every page with the installer licence box and the hyperscaler guide", async () => {
    for (const slug of slugs) {
      const model = loadCatalog().find((item) => item.slug === slug);
      if (model?.installer_policy?.status === "excluded") continue;
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
      expect(html, slug).toContain(`mailto:info@decisionmodels.io?subject=Local%20install%20request%20${slug}`);
      expect(html, slug).not.toMatch(COMMANDS);
      expect(html, slug).not.toContain("Manual, not covered");
      expect(html, slug).toContain("Run it on AWS, Azure or Google Cloud");
      expect(html, slug).toContain("Free for individuals and companies");
      expect(html, slug).toContain("your data never leaves your machines");
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

  it("says hardware is on request when the data has no size", async () => {
    const unknown = hardware.find((entry) => !entry.min && !loadCatalog().some((model) => model.slug === entry.slug));
    if (!unknown) return;
    expect(await render(unknown.slug)).toContain("Hardware requirements on request");
  });

  it("does not claim anything about hosting location or certifications", async () => {
    const html = await render(hardware[0].slug);
    expect(html).not.toMatch(/Helsinki|Finland|ISO 27001|SOC 2|certified/i);
  });
});
