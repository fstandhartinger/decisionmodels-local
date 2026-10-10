import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { afterEach, describe, expect, it } from "vitest";
import { benchmarkRank, displayCopy, hasExecutableInstallRecipe, installRecipeStatus, loadCatalog, publicCatalog, sanitizePublicText, sortedByBenchmark } from "../lib/catalog";
import { catalogRoot } from "../lib/catalog-root";

let temporary: string | undefined;
afterEach(() => { if (temporary) fs.rmSync(temporary, { recursive: true, force: true }); temporary = undefined; });

describe("catalogue loader", () => {
  it("does not label malformed or missing commands as executable install recipes", () => {
    expect(hasExecutableInstallRecipe({ install: { processes: [{ command: [""] }] } })).toBe(false);
    expect(installRecipeStatus({ install: { processes: [{ command: ["python"] }] } })).toBe("ready_unverified");
    expect(installRecipeStatus({ install: { processes: [] } })).toBe("documentation_only");
  });

  it("loads partial entries, applies safe defaults, and strips local recipe paths from public data", () => {
    temporary = fs.mkdtempSync(path.join(os.tmpdir(), "dm-catalog-"));
    fs.writeFileSync(path.join(temporary, "partial.json"), JSON.stringify({ slug: "partial-model", name: "Partial Model", variants: [{ id: "test", serve: { recipe_source: "/private/path", port: 8484 } }] }));
    fs.writeFileSync(path.join(temporary, "ignored.json"), "{");
    fs.writeFileSync(path.join(temporary, "wrong.json"), JSON.stringify({ slug: "invalid slug", name: "Invalid" }));
    const models = loadCatalog(temporary);
    expect(models).toHaveLength(1);
    expect(models[0]).toMatchObject({ author: "Author not listed", modalities: [], installer_policy: { status: "excluded" } });
    const publicSupported = publicCatalog([{ ...models[0], installer_policy: { status: "supported" } }])[0];
    expect((publicSupported.variants as Array<{ serve?: Record<string, unknown> }>)[0].serve).toBeUndefined();
  });
  it("removes internal prose and measurement notes from the public catalogue", () => {
    const models = [{ slug: "public-model", name: "Public Model", licence: { notes: "internal summary", evidence: ["/home/private/source.txt"] }, variants: [{ expected_speed: "BH card details", notes: "recipe NOTES", measured: { gpu: "UNVERIFIED", p50_ms: 12, source: "local path" } }] }];
    const model = publicCatalog(models)[0];
    expect(model.licence).toEqual({});
    expect(model.variants?.[0]).toEqual({ measured: { p50_ms: 12 }, install: { available: false, status: "documentation_only" } });
  });
  it("scrubs local paths and internal serving provenance embedded in public strings", () => {
    const [model] = publicCatalog([{ slug: "public-test", name: "Public test", description: "Served from /home/flori/jobs/private/serve.sh using BH recipe details" }]);
    expect(JSON.stringify(model)).not.toMatch(/\/home\/flori|BH recipe/i);
    expect(sanitizePublicText("Estimate on the BH measurement; serving script at C:\\private\\runner.py")).not.toMatch(/BH measurement|C:\\private/);
  });
  it("publishes recipe availability and verification state without serving commands or run provenance", () => {
    const [model] = publicCatalog([{ slug: "safe-recipe", name: "Safe recipe", variants: [{ id: "cuda", runtime_version: "torch 2.14 (BH Dockerfile)", gpu_arch_min: "UNVERIFIED (BH ran H100)", image: "private/image@sha256:abc", serve: { recipe_source: "/home/flori/jobs/private/source", port: 8484, steps: ["run the private serving script"] }, install: { processes: [{ command: ["python", "/home/flori/jobs/private/serve.py"] }], verified: { status: "verified", where: "RunPod private pod", notes: "internal receipt" } } }] }]);
    expect(model.variants?.[0].install).toEqual({ available: true, status: "tested", verified: { status: "verified" } });
    expect(JSON.stringify(model)).not.toMatch(/\/home\/flori|private pod|serve\.py|internal receipt|BH Dockerfile|BH ran|private\/image|serving script/i);
  });
  it("keeps excluded models neutral and omits ranks and hardware from the public API", () => {
    const [model] = publicCatalog([{ slug: "excluded-model", name: "Excluded model", benchmarks: { imagejevbench: { capability_rank: 6 } }, variants: [{ id: "cuda", min_vram_gb: 80 }], installer_policy: { status: "excluded", reason: "Internal licensing review note" } }]);
    expect(model).toEqual({ slug: "excluded-model", name: "Excluded model", installer_policy: { status: "excluded", reason: "This model is not offered in the installer while its licensing review is pending." } });
  });
  it("does not expose local paths or internal serving provenance from the real catalog", () => {
    const payload = JSON.stringify(publicCatalog(loadCatalog()));
    expect(payload).not.toMatch(/\/(?:home|tmp|opt|mnt|workspace)\/|[A-Za-z]:\\|BH recipe|BH Dockerfile|BH ran|BH copy|serving path|serve script/i);
  });
  it("returns an empty catalog when its directory is absent", () => {
    expect(loadCatalog("/path/that/does/not/exist/dm-catalog")).toEqual([]);
  });

  it("skips an empty working-directory catalog and finds the shared catalog above it", () => {
    temporary = fs.mkdtempSync(path.join(os.tmpdir(), "dm-catalog-shadow-"));
    const app = path.join(temporary, "app");
    fs.mkdirSync(path.join(app, "catalog"), { recursive: true });
    fs.symlinkSync(catalogRoot(), path.join(temporary, "catalog"), "dir");
    expect(catalogRoot(app, "")).toBe(path.join(temporary, "catalog"));
  });

  it("accepts catalog slugs containing version dots", () => {
    temporary = fs.mkdtempSync(path.join(os.tmpdir(), "dm-catalog-"));
    fs.writeFileSync(path.join(temporary, "bobcat.json"), JSON.stringify({ slug: "bobcat-flash-1.2", name: "Bobcat Flash 1.2" }));
    expect(loadCatalog(temporary).map((model) => model.slug)).toEqual(["bobcat-flash-1.2"]);
  });

  it("does not present a source rank as a capability rank", () => {
    const models = [{ slug: "rank-alias", name: "Rank Alias", benchmarks: { imagejevbench: { rank: 3 } } }];
    expect(benchmarkRank(models[0].benchmarks.imagejevbench)).toBeNull();
    expect(sortedByBenchmark(models, "imagejevbench").map((model) => model.slug)).toEqual(["rank-alias"]);
  });

  it("tidies split units and spelling in visible catalogue copy", () => {
    expect(displayCopy("About 59 ms p 50 on an H 100 with BF 16 weights from the installer catalog."))
      .toBe("About 59 ms p50 on an H100 with BF16 weights from the installer catalogue.");
  });
});
