import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import Page from "../app/models/[slug]/local/page";
import CloudPage from "../app/local/cloud/page";
import { licenceCopy, selfRunModels } from "../lib/self-run";
import { cloudInstanceFor } from "../lib/cloud-instances";

const render = async (slug: string) => renderToStaticMarkup(await Page({ params: Promise.resolve({ slug }) }));
describe("self-service guides", () => {
  it("gives Mammoth a pinned localhost vLLM command and secondary help", async () => {
    const html = await render("mammoth-1");
    expect(html).toContain("Run baselabs mammoth-1 yourself");
    expect(html).toContain("vllm serve baselabs/mammoth-1 --revision");
    expect(html).toContain("--host 127.0.0.1 --port 8000");
    expect(html).toContain('href="/local/cloud"');
    expect(html).not.toContain("dm-local plan mammoth-1");
    expect(html).not.toContain("dm-local install mammoth-1");
    expect(html).not.toContain("Local install on request");
    expect(html.indexOf("Run the public weights")).toBeLessThan(html.indexOf("<form"));
    expect(html).toMatch(/<details[^>]*><summary>Need help setting it up\?/);
    expect(html).toContain("Running the public weights yourself with vLLM needs no Decision Models licence");
  });
  it("links supported model pages to the cloud guide too", async () => {
    expect(await render("h2o-lightning-4b")).toContain('href="/local/cloud#aws"');
  });
  it("lists all three providers, SSH tunnels, cleanup and honest validation status", () => {
    const html = renderToStaticMarkup(CloudPage());
    for (const id of ["aws", "azure", "gcp"]) expect(html).toContain(`id="${id}"`);
    for (const command of ["aws ec2 run-instances", "az vm create", "gcloud compute instances create", "aws ec2 terminate-instances", "az group delete", "gcloud compute instances delete"]) expect(html).toContain(command);
    expect(html).toContain("not been run by us end-to-end");
    expect(html).toContain("Spot or Flex-start");
    expect(html).toContain("gcloud compute routers nats create");
    expect(html).toContain("gcloud compute routers delete");
  });
  it("withholds commands from gated models and adapters and pins every offered command", () => {
    for (const [slug, model] of Object.entries(selfRunModels())) {
      if (model.gated || model.adapter_base || model.runtime !== "vllm") expect(model.command, slug).toBeNull();
      if (model.adapter_base) expect(model.vram_gb, slug).toBeNull();
      if (model.command) {
        expect(model.revision, slug).toMatch(/^[a-f0-9]{40}$/);
        expect(model.command, slug).toContain(`--revision ${model.revision}`);
        expect(model.command, slug).toContain("--host 127.0.0.1");
      }
    }
  });
  it("selects only instances with enough known memory", () => {
    expect(cloudInstanceFor("aws", 70)?.name).toBe("p5.48xlarge");
    expect(cloudInstanceFor("azure", 100)).toBeUndefined();
    expect(cloudInstanceFor("gcp", null)).toBeUndefined();
  });
  it("treats non-commercial and mixed licence strings conservatively", () => {
    expect(licenceCopy("cc-by-nc-4.0")).toContain("research and personal use only");
    expect(licenceCopy("MIT")).toContain("Commercial use OK");
    expect(licenceCopy("MIT (code); weights restricted")).toContain("Licence unclear");
    expect(licenceCopy(null)).toContain("Licence unclear");
  });
});
