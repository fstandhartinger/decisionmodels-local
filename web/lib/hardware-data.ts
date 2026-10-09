import { catalogRoot } from "./catalog-root";
import fs from "node:fs";
import path from "node:path";
import { deviceQuotes, deviceStreetPrices, hasExecutableInstallRecipe, suggestDevice, type Device, type DeviceClass } from "@/lib/hardware-core.mjs";
import type { Model } from "@/lib/catalog";

export type HardwarePrices = { retrieved_utc?: string; devices?: Device[]; cloud?: CloudPrice[] };
export type CloudPrice = { provider?: string; instance?: string; gpu?: string; vram_gb?: number | null; usd_per_hour?: number; source?: string; date?: string; region?: string };

export function loadHardwarePrices(): HardwarePrices {
  try { return JSON.parse(fs.readFileSync(path.join(catalogRoot(), "hardware-prices.json"), "utf8")) as HardwarePrices; }
  catch { return { devices: [], cloud: [] }; }
}

export function loadDeviceClasses(): DeviceClass[] {
  try {
    const data = JSON.parse(fs.readFileSync(path.join(catalogRoot(), "device-classes.json"), "utf8")) as { classes?: DeviceClass[] };
    return Array.isArray(data.classes) ? data.classes : [];
  } catch { return []; }
}

export function loadSuggestions(): Record<string, ReturnType<typeof suggestDevice>> {
  try {
    const data = JSON.parse(fs.readFileSync(path.join(catalogRoot(), "hardware-suggestions.json"), "utf8")) as { suggestions?: Record<string, ReturnType<typeof suggestDevice>> };
    return data.suggestions ?? {};
  } catch { return {}; }
}

export function quoteSummary(device: Device, definition?: DeviceClass) {
  const street = deviceStreetPrices(device, definition);
  const quotes = deviceQuotes(device, definition);
  return Object.entries(quotes).map(([currency, quote]) => ({
    currency,
    street: street[currency] ?? null,
    quote,
    sources: (device.prices ?? []).filter((price) => price.currency === currency)
  }));
}

export function suggestedDeviceFor(model: Model, prices = loadHardwarePrices()) {
  return suggestDevice(model, prices.devices ?? [], loadDeviceClasses());
}

export function classRunsToday(models: Model[], devices: Device[], definition: DeviceClass): string {
  const members = devices.filter((device) => definition.device_ids.includes(device.id));
  const names = models.filter((model) => {
    if (!model.lists?.some((list) => list === "jevbench-top10" || list === "imagejevbench-top10")) return false;
    if (!["supported", "supported_noncommercial_only"].includes(model.installer_policy?.status ?? "")) return false;
    return (model.variants ?? []).some((variant) => {
      if (!hasExecutableInstallRecipe(variant) || variant.install?.verified?.status !== "verified") return false;
      if (!(variant.platforms ?? []).some((platform) => definition.platforms.includes(platform))) return false;
      const needed = definition.id === "apple-silicon" ? variant.min_ram_gb : variant.recommended_vram_gb;
      if (typeof needed !== "number" || !Number.isFinite(needed) || needed <= 0) return false;
      if (["jetson", "android"].includes(definition.id)) {
        const precision = String(variant.precision ?? "").toLowerCase();
        if ((model.params?.total_b ?? Infinity) > 4 || !/q\d|quant|int[48]|fp8|nvfp4/.test(precision)) return false;
      }
      return members.some((device) => typeof device.memory_gb === "number" && Number.isFinite(device.memory_gb) && device.memory_gb >= needed);
    });
  }).map((model) => model.name);
  if (names.length) {
    const shown = names.slice(0, 5).join(", ");
    return `Install tested: ${shown}${names.length > 5 ? `, plus ${names.length - 5} more` : ""}.`;
  }
  const recipes = models.filter((model) => (model.variants ?? []).some((variant) =>
    hasExecutableInstallRecipe(variant) && variant.install?.verified?.status !== "verified"
      && (variant.platforms ?? []).some((platform) => definition.platforms.includes(platform))
      && members.some((device) => {
        const needed = definition.id === "apple-silicon" ? variant.min_ram_gb : variant.recommended_vram_gb;
        return typeof needed === "number" && typeof device.memory_gb === "number" && Number.isFinite(device.memory_gb) && device.memory_gb >= needed;
      })
  )).map((model) => model.name);
  const estimate = recipes.length ? ` Recipe available but unverified for ${recipes.slice(0, 4).join(", ")}${recipes.length > 4 ? `, plus ${recipes.length - 4} more` : ""}.` : "";
  return `Install tested: none for this platform and memory tier.${estimate}`;
}

export function cloudRequirement(model: Model): number | null {
  if (model.installer_policy?.status === "excluded") return null;
  const values = (model.variants ?? [])
    .filter((variant) => (variant.platforms ?? []).includes("linux-nvidia"))
    .map((variant) => variant.recommended_vram_gb)
    .filter((value): value is number => Number.isFinite(value) && Number(value) > 0)
    .map(Number);
  return values.length ? Math.min(...values) : null;
}

export function cloudOptionsFor(model: Model, prices = loadHardwarePrices()): CloudPrice[] {
  const needed = cloudRequirement(model);
  if (needed === null) return [];
  return (prices.cloud ?? [])
    .filter((row) => ["runpod", "aws", "gcp", "azure", "coreweave"].includes(String(row.provider).toLowerCase()))
    .filter((row) => typeof row.source === "string" && /^https?:\/\//i.test(row.source))
    .filter((row) => typeof row.vram_gb === "number" && Number.isFinite(row.vram_gb) && row.vram_gb >= needed)
    .filter((row) => typeof row.usd_per_hour === "number" && Number.isFinite(row.usd_per_hour))
    .map((row) => ({ ...row, source: sourceUrl(row.source) }))
    .sort((a, b) => Number(a.usd_per_hour) - Number(b.usd_per_hour));
}

export function cheapestCloudOptionFor(model: Model, prices = loadHardwarePrices()): CloudPrice | undefined {
  return cloudOptionsFor(model, prices)[0];
}

export function money(value: number | null | undefined, currency: string) {
  if (!Number.isFinite(value)) return "Not available";
  try { return new Intl.NumberFormat("en", { style: "currency", currency, maximumFractionDigits: 0 }).format(value as number); }
  catch { return `${currency} ${value}`; }
}

export function hourlyMoney(value: number | null | undefined) {
  if (!Number.isFinite(value)) return "Not available";
  return new Intl.NumberFormat("en", { style: "currency", currency: "USD", minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(value as number);
}

export function publicCloudGpuName(value?: string) {
  if (!value) return "GPU";
  const match = value.match(/RTX\s+PRO\s+6000(?:\s+Blackwell)?|RTX\s+5090|RTX\s+4090|L40S|H100|H200|A100|L4/i);
  return match?.[0] ?? "GPU";
}

export function publicCloudProviderName(value?: string) {
  const names: Record<string, string> = { runpod: "RunPod", aws: "AWS", gcp: "GCP", azure: "Azure", coreweave: "CoreWeave" };
  return names[String(value ?? "").toLowerCase()] ?? "Cloud provider";
}

export function publicCloudInstanceName(value?: string) {
  return (value ?? "Instance not listed").replace(/\s*\(per GPU\s*=.*?\)/i, "").trim();
}

export function sourceUrl(value?: string): string | undefined {
  return value?.match(/^https?:\/\/[^\s]+/i)?.[0];
}

export function dateText(value: unknown) {
  if (typeof value !== "string" || value === "unknown" || !value) return "date not supplied";
  return value.slice(0, 10);
}

export function sourcePublisher(value?: string) {
  try { return new URL(sourceUrl(value) ?? "").hostname.replace(/^www\./, "") || "Source not listed"; }
  catch { return "Source not listed"; }
}
