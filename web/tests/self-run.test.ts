import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import Page from "../app/models/[slug]/local/page";
import CloudPage from "../app/local/cloud/page";
import { licenceCopy, localRequestCurl, publicRepoId, selfRunModels } from "../lib/self-run";
import { cloudInstanceFor, cloudServeCommand } from "../lib/cloud-instances";
import { getModel, isInstallerSupported } from "../lib/catalog";

const render = async (slug: string) => renderToStaticMarkup(await Page({ params: Promise.resolve({ slug }) }));
describe("self-service guides", () => {
  it("gives Clef a pinned localhost vLLM command and secondary help", async () => {
    const html = await render("clef");
    expect(html).toContain("Run Clef yourself");
    expect(html).toContain("vllm serve Cloudflare/clef --revision");
    expect(html).toContain("--host 127.0.0.1 --port 8000");
    expect(html).toContain('href="/local/cloud?model=clef"');
    expect(html).not.toContain("dm-local plan clef");
    expect(html).not.toContain("dm-local install clef");
    expect(html).not.toContain("Local install on request");
    expect(html.indexOf("Run the public weights")).toBeLessThan(html.indexOf("<form"));
    expect(html).toMatch(/<details[^>]*><summary>Need help setting it up\?/);
    expect(html).toContain("Running the public weights yourself with vLLM needs no Decision Models licence");
  });
  it("keeps author-server models off the stock vLLM path, with honest pending-recipe status", async () => {
    for (const slug of ["mammoth-1", "vllm-sr-d3", "vllm-sr-d3-turbo", "pplx-decider-v1-1-27b", "fastino-glide-1.2-open", "basal-omni-1.0-ultra", "knowline-31b-gen1"]) {
      const html = await render(slug);
      if (!isInstallerSupported(getModel(slug))) {
        expect(html).toContain("Installer recipe in verification");
        expect(html).not.toContain(`dm-local install ${slug}`);
      }
      expect(html).not.toContain("vllm serve ");
      expect(html).not.toContain("/v1/chat/completions");
      const cloud = renderToStaticMarkup(await CloudPage({ searchParams: Promise.resolve({ model: slug }) }));
      expect(cloud).not.toContain("vllm serve");
      expect(cloud).not.toContain("pip install vllm");
      expect(cloud).toContain("author’s serving runtime");
      expect(html).not.toContain("Local install on request");
    }
    expect(await render("clef")).not.toContain("Installer recipe in verification");
  });
  it("links supported model pages to the cloud guide too", async () => {
    expect(await render("h2o-lightning-4b")).toContain('href="/local/cloud?model=h2o-lightning-4b#aws"');
  });
  it("lists all three providers, SSH tunnels, cleanup and honest validation status", async () => {
    const html = renderToStaticMarkup(await CloudPage({}));
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
    expect(cloudInstanceFor("aws", 70)?.name).toBe("p5.4xlarge");
    expect(cloudInstanceFor("azure", 100)?.gpuCount).toBe(2);
    expect(cloudInstanceFor("gcp", null)).toBeUndefined();
  });
  it("keeps the estimate within vLLM's default 90 % GPU memory use", () => {
    expect(cloudInstanceFor("aws", 24)?.name).toBe("g6e.xlarge");
    expect(cloudInstanceFor("aws", 21.6)?.name).toBe("g6.xlarge");
    expect(cloudInstanceFor("aws", 76.6)?.name).toBe("p5.48xlarge");
    expect(cloudInstanceFor("azure", 76.6)?.name).toBe("Standard_NC40ads_H100_v5");
    expect(cloudInstanceFor("gcp", 76.6)?.name).toBe("a2-ultragpu-2g");
    for (const provider of ["aws", "azure", "gcp"]) for (const memory of [10, 24, 40, 67.8, 72, 76.6, 100, 150]) {
      const instance = cloudInstanceFor(provider, memory);
      if (instance) expect(instance.memory * 0.9).toBeGreaterThanOrEqual(memory);
    }
  });
  it("withholds unreviewed custom architectures and base-less adapters", async () => {
    const models = selfRunModels();
    for (const slug of ["vera-large", "d1a-gemma4-e4b", "watersheep", "decision-2-0-vega-27b", "openjev-4b-v5"]) {
      expect(models[slug], slug).toBeDefined();
      expect(models[slug].command, slug).toBeNull();
      expect(await render(slug)).not.toContain("vllm serve ");
    }
    expect(models["vera-large"].missing).toContain("own architecture (VeraForDecision)");
    expect(models["d1a-gemma4-e4b"].vram_gb).toBeNull();
    for (const slug of ["mammoth-1", "knowline-31b-gen1"]) expect(models[slug].command).toContain("vllm serve ");
    for (const model of Object.values(models)) expect(model.command ?? "").not.toContain("--trust-remote-code");
  });
  it.each(["clef", "h2o-lightning-4b"])("keeps %s sizing, VM creation and serving together", async (slug) => {
    const facts = selfRunModels()[slug];
    const html = renderToStaticMarkup(await CloudPage({ searchParams: Promise.resolve({ model: slug }) }));
    const local = await render(slug);
    const memory = slug === "h2o-lightning-4b" ? 24 : facts.vram_gb!; // Installer card uses its recorded 24 GB minimum.
    expect(html).toContain(`GPU memory needed: ${memory} GB`);
    for (const [provider, flag] of [["aws", "--instance-type"], ["azure", "--size"], ["gcp", "--machine-type"]]) {
      const instance = cloudInstanceFor(provider, memory)!;
      expect(instance.gpuCount).toBe(1);
      expect(instance.gpuMemory * 0.9).toBeGreaterThanOrEqual(memory);
      const section = html.split(`id="${provider}"`)[1].split("</section>")[0];
      expect(section).toContain(`INSTANCE_TYPE=${instance.name}`);
      expect(section).toContain(`${flag} &quot;$INSTANCE_TYPE&quot;`);
      expect(section).toContain(facts.command!);
      expect(section).not.toContain("--tensor-parallel-size");
      expect(local).toContain(instance.name);
      expect(local).toContain(`/local/cloud?model=${slug}#${provider}`);
    }
    if (slug === "clef") expect(cloudInstanceFor("aws", facts.vram_gb)?.name).toBe("p5.4xlarge");
  });
  it("requires explicit size selection in generic creation commands", async () => {
    const html = renderToStaticMarkup(await CloudPage({}));
    expect(html.match(/INSTANCE_TYPE=REPLACE_WITH_INSTANCE_FROM_TABLE/g)).toHaveLength(3);
    expect(html.indexOf("<table>")).toBeLessThan(html.indexOf("INSTANCE_TYPE="));
    expect(html).not.toContain("vllm serve ");
  });
  it("adds tensor parallelism only for a fitting multi-GPU instance", () => {
    for (const provider of ["aws", "azure", "gcp"]) {
      const instance = cloudInstanceFor(provider, 125.8)!;
      expect(instance.gpuCount).toBeGreaterThan(1);
      expect(instance.memory * 0.9).toBeGreaterThanOrEqual(125.8);
      expect(cloudServeCommand("vllm serve example --host 127.0.0.1", instance)).toContain(`--tensor-parallel-size ${instance.gpuCount}`);
    }
    expect(cloudInstanceFor("aws", 1000)).toBeUndefined();
    expect(cloudServeCommand(null, cloudInstanceFor("aws", 20))).toBeNull();
  });
  it("treats non-commercial and mixed licence strings conservatively", () => {
    expect(licenceCopy("cc-by-nc-4.0")).toContain("research and personal use only");
    expect(licenceCopy("MIT")).toContain("Commercial use OK");
    expect(licenceCopy("MIT (code); weights restricted")).toContain("Licence unclear");
    expect(licenceCopy(null)).toContain("Licence unclear");
  });
  it("never shows internal paths: maps cache paths to repo ids and hides everything else", () => {
    expect(publicRepoId("/workspace/hf/hub/models--Qwen--Qwen3.5-9B/snapshots/c2022abc")).toBe("Qwen/Qwen3.5-9B");
    expect(publicRepoId("/workspace/hf/hub/models--Qwen--Qwen3.5-9B")).toBe("Qwen/Qwen3.5-9B");
    expect(publicRepoId("google/gemma-4-12B-it")).toBe("google/gemma-4-12B-it");
    for (const bad of ["/workspace/models/local-base", "../x/y", "/tmp/a/b", "plainname", "", null, undefined, "a/b/c"]) expect(publicRepoId(bad as string | null | undefined), String(bad)).toBeUndefined();
  });
  it("renders adapter bases as repo ids and no workspace paths anywhere", async () => {
    const models = selfRunModels();
    for (const [slug, model] of Object.entries(models)) if (model.adapter_base) expect(await render(slug), slug).not.toContain("/workspace/");
    const imajev = models["imajev-9b"];
    if (imajev?.adapter_base?.startsWith("/workspace/")) expect(await render("imajev-9b")).toContain(publicRepoId(imajev.adapter_base)!);
  });
  it("shows an untested localhost request with the exact repo id after the vLLM command", async () => {
    const html = await render("clef");
    expect(html).toContain("http://localhost:8000/v1/chat/completions");
    expect(html).toContain("Cloudflare/clef");
    expect(html).toContain("We have not tested this request");
    expect(html.indexOf("vllm serve ")).toBeLessThan(html.indexOf("/v1/chat/completions"));
    expect(JSON.parse(/-d '(.*)'$/.exec(localRequestCurl("a/b"))![1]).model).toBe("a/b");
    expect(await render("watersheep")).not.toContain("/v1/chat/completions");
  });
  it("drops the purchase button where the installer does not cover the model", async () => {
    const html = await render("clef");
    expect(html).not.toContain("Buy company licence");
    expect(html).toContain("The dm-local installer does not cover this model yet. The licence is only needed if you use the installer.");
    expect(html).toContain('href="/local/licence"');
    expect(await render("h2o-lightning-4b")).toContain("Buy company licence");
  });
});
