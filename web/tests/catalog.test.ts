import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { afterEach, describe, expect, it } from "vitest";
import { benchmarkRank, loadCatalog, publicCatalog, sortedByBenchmark } from "../lib/catalog";

let temporary: string | undefined;
afterEach(() => { if (temporary) fs.rmSync(temporary, { recursive: true, force: true }); temporary = undefined; });

describe("catalogue loader", () => {
  it("loads partial entries, applies safe defaults, and strips local recipe paths from public data", () => {
    temporary = fs.mkdtempSync(path.join(os.tmpdir(), "dm-catalog-"));
    fs.writeFileSync(path.join(temporary, "partial.json"), JSON.stringify({ slug: "partial-model", name: "Partial Model", variants: [{ id: "test", serve: { recipe_source: "/private/path", port: 8484 } }] }));
    fs.writeFileSync(path.join(temporary, "ignored.json"), "{");
    fs.writeFileSync(path.join(temporary, "wrong.json"), JSON.stringify({ slug: "invalid slug", name: "Invalid" }));
    const models = loadCatalog(temporary);
    expect(models).toHaveLength(1);
    expect(models[0]).toMatchObject({ author: "Author not listed", modalities: [], installer_policy: { status: "excluded" } });
    expect((publicCatalog(models)[0].variants as Array<{ serve: Record<string, unknown> }>)[0].serve).toEqual({ port: 8484 });
  });
  it("returns an empty catalog when its directory is absent", () => {
    expect(loadCatalog("/path/that/does/not/exist/dm-catalog")).toEqual([]);
  });

  it("accepts catalog slugs containing version dots", () => {
    temporary = fs.mkdtempSync(path.join(os.tmpdir(), "dm-catalog-"));
    fs.writeFileSync(path.join(temporary, "bobcat.json"), JSON.stringify({ slug: "bobcat-flash-1.2", name: "Bobcat Flash 1.2" }));
    expect(loadCatalog(temporary).map((model) => model.slug)).toEqual(["bobcat-flash-1.2"]);
  });

  it("uses a source rank field when capability_rank is absent", () => {
    const models = [{ slug: "rank-alias", name: "Rank Alias", benchmarks: { imagejevbench: { rank: 3 } } }];
    expect(benchmarkRank(models[0].benchmarks.imagejevbench)).toBe(3);
    expect(sortedByBenchmark(models, "imagejevbench").map((model) => model.slug)).toEqual(["rank-alias"]);
  });
});
