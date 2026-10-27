import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import Page, { generateMetadata, generateStaticParams } from "../app/models/[slug]/local/page";
import { localRequestModels } from "../lib/local-request-models";

const props = (slug: string) => ({ params: Promise.resolve({ slug }) });
describe("local setup request fallback", () => {
  it("covers all current hub model names without adding installer support", async () => {
    const names = localRequestModels();
    expect(Object.keys(names)).toHaveLength(293);
    const slugs = new Set(generateStaticParams().map((item) => item.slug));
    for (const slug of Object.keys(names)) expect(slugs.has(slug)).toBe(true);
    for (const slug of ["h2o-lightning-31b", "basal-omni-1.0-ultra", "dopest-1.0-31b", "jeff-1-1-medium", "arcbright-elf-1-31b", "sieve-31b-v2", "metask-jev-rain-31b-trained-v3"]) {
      const html = renderToStaticMarkup(await Page(props(slug)));
      expect(html).toContain(names[slug]);
      expect(html).toContain("Request local setup");
      expect(html).toContain(`name="models" value="${slug}"`);
      expect(html).toContain('name="request_kind" value="local"');
      expect(html).not.toContain("Buy company licence");
      expect(html).not.toContain("dm-local install");
      expect(html).not.toContain("Machine of interest");
    }
  });
  it("treats a future valid reference as explicitly unverified and noindex", async () => {
    const slug = "future-model-reference-31b";
    const html = renderToStaticMarkup(await Page(props(slug)));
    expect(html).toContain("Unverified model reference");
    expect(html).toContain("does not confirm that the model or its weights are available");
    expect(html).toContain(`name="models" value="${slug}"`);
    expect((await generateMetadata(props(slug))).robots).toMatchObject({ index: false });
  });
  it.each(["UpperCase", "../escape", "bad_slug", "a".repeat(82)])("keeps invalid slug %s a 404", async (slug) => {
    await expect(Page(props(slug))).rejects.toThrow(/404/);
  });
});
