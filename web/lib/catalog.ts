import { catalogRoot } from "./catalog-root";
import fs from "node:fs";
import path from "node:path";

export type ModelVariant = {
  id?: string;
  precision?: string;
  benchmarked?: boolean;
  runtime?: string;
  runtime_version?: string;
  gpu_arch_min?: string | null;
  image?: unknown;
  serve?: Record<string, unknown>;
  platforms?: string[];
  min_vram_gb?: number;
  recommended_vram_gb?: number;
  min_ram_gb?: number;
  disk_gb?: number;
  expected_speed?: string;
  install?: { available?: boolean; status?: "tested" | "ready_unverified" | "documentation_only"; processes?: { command?: string[] }[]; verified?: { status?: string; [key: string]: unknown }; [key: string]: unknown };
  measured?: { gpu?: string; p50_ms?: number; source?: string };
  notes?: string;
};

export function hasExecutableInstallRecipe(variant: ModelVariant): boolean {
  return Array.isArray(variant.install?.processes)
    && variant.install.processes.length > 0
    && variant.install.processes.every((process) => Array.isArray(process.command)
      && process.command.length > 0
      && typeof process.command[0] === "string" && process.command[0].trim().length > 0
      // Later arguments may legitimately be empty strings (e.g. `--cors-origins ""`).
      && process.command.every((argument) => typeof argument === "string"));
}

export function installRecipeStatus(variant: ModelVariant): "tested" | "ready_unverified" | "documentation_only" {
  if (!hasExecutableInstallRecipe(variant)) return "documentation_only";
  return variant.install?.verified?.status === "verified" ? "tested" : "ready_unverified";
}

export function hasAnyExecutableInstallRecipe(model: Model): boolean {
  return (model.variants ?? []).some(hasExecutableInstallRecipe);
}

export type Model = {
  schema?: string;
  slug: string;
  name: string;
  author?: string;
  description?: string;
  lists?: string[];
  benchmarks?: {
    jevbench?: { version?: string; capability_rank?: number; rank?: number; capability?: number; p50_s_raw?: number; page?: string };
    imagejevbench?: { version?: string; capability_rank?: number; rank?: number; capability?: number; p50_s_raw?: number; page?: string };
  };
  modalities?: string[];
  weights?: { repo?: string; revision?: string; url?: string; gated?: boolean };
  params?: { total_b?: number; active_b?: number };
  licence?: { spdx?: string; commercial_use?: string; redistribution?: string; notes?: string; evidence?: string[] };
  jev_distillation?: { display_note?: string; status?: string; evidence?: string; url?: string };
  installer_policy?: { status?: string; reason?: string };
  variants?: ModelVariant[];
  [key: string]: unknown;
};

/** Installer support is data-driven: the catalogue policy allows install and an executable recipe exists. */
export function isInstallerSupported(model: Model | undefined): boolean {
  if (!model) return false;
  const status = model.installer_policy?.status;
  return (status === "supported" || status === "supported_noncommercial_only") && hasAnyExecutableInstallRecipe(model);
}

const modelDirectory = path.join(catalogRoot(), "models");

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
      if (!isModel(parsed) || (parsed as { hidden?: boolean }).hidden === true) continue;
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

export function sanitizePublicText(value: string): string {
  return value
    .replace(/(?:\/(?:home|tmp|opt|mnt|workspace|root|var|srv|Users|private|Volumes)\/[^\s,;)}]+|[A-Za-z]:\\[^\s,;)}]+|\\\\[^\s,;)}]+)/g, "")
    .replace(/\s+on\s+(?:the\s+)?(?:BH|Benchmark Heaven) (?:measurement(?: box)?|card|H\s*100|RTX(?:\s+PRO)?\s*(?:6000|4090|5090)|L40S|H100|H200|A100|L4)\b/gi, " on the measured GPU")
    .replace(/\b(?:BH|Benchmark Heaven) (?:recipe|serving path|runner|serve script|Dockerfile|meta(?:\.json)?|copy)\b[^.;)]*/gi, "")
    .replace(/\(\s*\)/g, "")
    .replace(/\s{2,}/g, " ").trim();
}

export function publicCatalog(models = loadCatalog()): Model[] {
  const internalKeys = new Set(["recipe_source", "notes", "note", "evidence", "expected_speed", "portable_notes", "worker_proposal", "decided_by", "gpu_arch_min", "runtime_version", "image", "serve", "source"]);
  const stripInternalCopy = (value: unknown, parentKey = ""): unknown => {
    if (Array.isArray(value)) return value.map((child) => stripInternalCopy(child, parentKey)).filter((child) => child !== undefined);
    if (typeof value === "string") return sanitizePublicText(value) || undefined;
    if (!value || typeof value !== "object") return value;
    const clean = Object.fromEntries(Object.entries(value)
      .filter(([key]) => !internalKeys.has(key) && !(parentKey === "measured" && key === "gpu"))
      .filter(([key]) => key !== "install")
      .map(([key, child]) => [key, stripInternalCopy(child, key)])
      .filter(([, child]) => child !== undefined));
    if (parentKey !== "variants") return clean;
    const variant = value as ModelVariant;
    const recipeStatus = installRecipeStatus(variant);
    const verified = variant.install?.verified?.status;
    return {
      ...clean,
      install: {
        available: hasExecutableInstallRecipe(variant),
        status: recipeStatus,
        ...(verified ? { verified: { status: verified } } : {})
      }
    };
  };
  return models.map((model) => {
    if (model.installer_policy?.status === "excluded") return {
      slug: model.slug,
      name: model.name,
      installer_policy: { status: "excluded", reason: "This model is not offered in the installer while its licensing review is pending." }
    };
    return stripInternalCopy(model) as Model;
  });
}

export function sortedByBenchmark(models: Model[], benchmark: "jevbench" | "imagejevbench"): Model[] {
  return models
    .filter((model) => Boolean(model.benchmarks?.[benchmark]))
    .sort((a, b) => {
      const left = benchmarkRank(a.benchmarks?.[benchmark]) ?? Infinity;
      const right = benchmarkRank(b.benchmarks?.[benchmark]) ?? Infinity;
      return left - right || a.name.localeCompare(b.name);
    });
}

export function benchmarkRank(benchmark?: { capability_rank?: number; rank?: number }) {
  const rank = benchmark?.capability_rank;
  return Number.isFinite(rank) ? rank as number : null;
}

export function minimumVram(model: Model): number | null {
  const values = (model.variants ?? []).map((variant) => variant.min_vram_gb).filter((value): value is number => Number.isFinite(value));
  return values.length ? Math.min(...values) : null;
}
