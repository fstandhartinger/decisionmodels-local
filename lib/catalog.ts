import fs from "node:fs";
import path from "node:path";

export type ModelVariant = {
  id?: string;
  precision?: string;
  benchmarked?: boolean;
  runtime?: string;
  runtime_version?: string;
  platforms?: string[];
  min_vram_gb?: number;
  recommended_vram_gb?: number;
  min_ram_gb?: number;
  disk_gb?: number;
  expected_speed?: string;
  measured?: { gpu?: string; p50_ms?: number; source?: string };
  notes?: string;
};

export type Model = {
  schema?: string;
  slug: string;
  name: string;
  author?: string;
  description?: string;
  lists?: string[];
  benchmarks?: {
    jevbench?: { version?: string; capability_rank?: number; rank?: number; capability?: number; page?: string };
    imagejevbench?: { version?: string; capability_rank?: number; rank?: number; capability?: number; page?: string };
  };
  modalities?: string[];
  weights?: { repo?: string; revision?: string; url?: string; gated?: boolean };
  params?: { total_b?: number; active_b?: number };
  licence?: { spdx?: string; commercial_use?: string; redistribution?: string; notes?: string; evidence?: string[] };
  jev_distillation?: { status?: string; evidence?: string; url?: string };
  installer_policy?: { status?: string; reason?: string };
  variants?: ModelVariant[];
  [key: string]: unknown;
};

const modelDirectory = path.join(process.cwd(), "catalog", "models");

function isModel(value: unknown): value is Model {
  if (!value || typeof value !== "object") return false;
  const record = value as Record<string, unknown>;
  return typeof record.slug === "string" && /^[a-z0-9](?:[a-z0-9.-]{0,118}[a-z0-9])?$/.test(record.slug) && typeof record.name === "string";
}

export function loadCatalog(directory = modelDirectory): Model[] {
  let filenames: string[];
  try {
    filenames = fs.readdirSync(directory).filter((name) => name.endsWith(".json")).sort();
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code === "ENOENT") return [];
    throw error;
  }
  const found = new Map<string, Model>();
  for (const filename of filenames) {
    try {
      const parsed: unknown = JSON.parse(fs.readFileSync(path.join(directory, filename), "utf8"));
      if (!isModel(parsed)) continue;
      found.set(parsed.slug, {
        ...parsed,
        author: parsed.author ?? "Author not listed",
        lists: Array.isArray(parsed.lists) ? parsed.lists : [],
        modalities: Array.isArray(parsed.modalities) ? parsed.modalities : [],
        variants: Array.isArray(parsed.variants) ? parsed.variants : [],
        installer_policy: parsed.installer_policy ?? { status: "excluded", reason: "No local installer policy is recorded." }
      });
    } catch (error) {
      if (error instanceof SyntaxError) continue;
      throw error;
    }
  }
  return [...found.values()].sort((a, b) => a.name.localeCompare(b.name));
}

export function getModel(slug: string): Model | undefined {
  return loadCatalog().find((model) => model.slug === slug);
}

export function publicCatalog(models = loadCatalog()): Model[] {
  const stripRecipePaths = (value: unknown): unknown => {
    if (Array.isArray(value)) return value.map(stripRecipePaths);
    if (!value || typeof value !== "object") return value;
    return Object.fromEntries(Object.entries(value).filter(([key]) => key !== "recipe_source").map(([key, child]) => [key, stripRecipePaths(child)]));
  };
  return models.map((model) => stripRecipePaths(model) as Model);
}

export function sortedByBenchmark(models: Model[], benchmark: "jevbench" | "imagejevbench"): Model[] {
  return models
    .filter((model) => benchmarkRank(model.benchmarks?.[benchmark]) !== null)
    .sort((a, b) => (benchmarkRank(a.benchmarks?.[benchmark]) ?? Infinity) - (benchmarkRank(b.benchmarks?.[benchmark]) ?? Infinity));
}

export function benchmarkRank(benchmark?: { capability_rank?: number; rank?: number }) {
  const rank = benchmark?.capability_rank ?? benchmark?.rank;
  return Number.isFinite(rank) ? rank as number : null;
}

export function minimumVram(model: Model): number | null {
  const values = (model.variants ?? []).map((variant) => variant.min_vram_gb).filter((value): value is number => Number.isFinite(value));
  return values.length ? Math.min(...values) : null;
}
