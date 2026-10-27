import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import HardwarePage from "../app/hardware/page";

async function render(model?: string) {
  return renderToStaticMarkup(await HardwarePage({ searchParams: Promise.resolve({ model }) }));
}

describe("hardware requested model", () => {
  it.each(["pplx-decider-v1-1-27b", "jpt-9b", "vllm-sr-d3", "h2o-lightning-31b"])("keeps %s selected without inventing model requirements", async (slug) => {
    const html = await render(slug);
    expect(html).toContain(`Requested model: ${slug}`);
    expect(html).toMatch(new RegExp(`name="models"[^>]*checked=""[^>]*value="${slug}"`));
    expect(html).not.toContain(`href="/models/${slug}/local"`);
  });
  it("preserves the catalog selection and requirements link", async () => {
    const html = await render("quyet-1-0-large");
    expect(html).toContain("Selected model: Quyet-1.0-Large");
    expect(html).not.toContain("Requested model:");
    expect(html).toMatch(/name="models"[^>]*checked=""[^>]*value="quyet-1-0-large"/);
  });
  it.each([undefined, "../model", "a".repeat(82), "<script>"])("ignores invalid or absent requested slugs: %s", async (slug) => {
    expect(await render(slug)).not.toContain("Requested model:");
  });
});
