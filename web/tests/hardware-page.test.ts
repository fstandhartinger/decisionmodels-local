import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import HardwarePage from "../app/hardware/page";
import { deviceMemoryGb } from "../lib/hardware-tiers";

async function render(model?: string, device?: string, requested?: string) {
  return renderToStaticMarkup(await HardwarePage({ searchParams: Promise.resolve({ model, device, requested }) }));
}

describe("hardware requested model", () => {
  it("confirms only the requested=1 flow and illustrates each device", async () => {
    const html = await render("mammoth-1", undefined, "1");
    expect(html).toContain("Request received — baselabs mammoth-1 on pre-installed hardware.");
    expect(html).toContain("If you just sent a request for baselabs mammoth-1, we have it and will answer by email. These options are being introduced, so requests are answered by hand for now.");
    expect(html).not.toContain("within one business day");
    expect(await render("mammoth-1")).not.toContain("Request received");
    expect(await render("mammoth-1", undefined, "0")).not.toContain("Request received");
    expect(await render(undefined, undefined, "1")).not.toContain("Request received");
    for (const name of ["edge", "desk", "workstation", "rack"]) expect(html).toContain(`/hardware/${name}.svg`);
  });
  it.each(["mammoth-1", "jpt-9b", "dopest-1.0-31b", "h2o-lightning-31b"])("keeps %s selected without inventing model requirements", async (slug) => {
    const html = await render(slug);
    expect(html).toContain(`Requested model: ${slug}`);
    expect(html).toMatch(new RegExp(`name="models"[^>]*checked=""[^>]*value="${slug}"`));
  });
  it("falls back to the public-weights facts for models outside the installer catalogue", async () => {
    const html = await render("mammoth-1");
    expect(html).toContain("Selected model: baselabs mammoth-1");
    expect(html).toContain("About 67.8 GB of GPU memory");
    expect(html).toContain('href="/models/mammoth-1/local"');
    expect(html).toMatch(/about 67.8 GB needed; fits in the 96 GB GPU memory/);
    expect(html).toMatch(/about 67.8 GB needed; more than this device offers/);
    expect(await render("quyet-1-0-large")).not.toContain("GB needed;");
  });
  it("parses device memory labels", () => {
    expect(deviceMemoryGb("96–256 GB unified (M5 Ultra)")).toBe(96);
    expect(deviceMemoryGb("32 GB GPU memory")).toBe(32);
    expect(deviceMemoryGb("varies")).toBeNull();
  });
  it("preserves the catalog selection and requirements link", async () => {
    const html = await render("quyet-1-0-large");
    expect(html).toContain("Selected model: Quyet-1.0-Large");
    expect(html).not.toContain("Requested model:");
    expect(html).toMatch(/name="models"[^>]*checked=""[^>]*value="quyet-1-0-large"/);
  });
  it("offers pilot interest per machine and preserves both machine and model selections", async () => {
    const html = await render("quyet-1-0-large", "jetson-orin-nano-super");
    expect(html).toContain("Coming soon");
    expect(html).toContain("Interested in becoming a pilot customer");
    expect(html).toContain('href="/hardware?device=jetson-orin-nano-super&amp;model=quyet-1-0-large#request"');
    expect(html).toMatch(/value="jetson-orin-nano-super" selected=""/);
    expect(html).toMatch(/name="models"[^>]*checked=""[^>]*value="quyet-1-0-large"/);
    expect(html).toContain("Register pilot interest");
    expect(html).not.toContain("RTX 5090, today");
    expect(html).not.toContain("Pre-installed by us on request, as a complete workstation");
    expect(html).toContain("subject to feasibility and availability");
  });
  it("does not accept arbitrary hardware selections from the URL", async () => {
    const html = await render(undefined, "not-a-real-machine");
    expect(html).not.toContain("not-a-real-machine");
    expect(html).toMatch(/value="" selected=""/);
  });
  it.each([undefined, "../model", "a".repeat(82), "<script>"])("ignores invalid or absent requested slugs: %s", async (slug) => {
    expect(await render(slug)).not.toContain("Requested model:");
  });
});
