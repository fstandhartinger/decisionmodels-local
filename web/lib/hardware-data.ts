import { catalogRoot } from "./catalog-root";
import fs from "node:fs";
import path from "node:path";
import { deviceQuotes, deviceStreetPrices, suggestDevice, type Device } from "@/lib/hardware-core.mjs";
import type { Model } from "@/lib/catalog";

export type HardwarePrices = { retrieved_utc?: string; devices?: Device[]; cloud?: Array<Record<string, unknown>> };

export function loadHardwarePrices(): HardwarePrices {
  try { return JSON.parse(fs.readFileSync(path.join(catalogRoot(), "hardware-prices.json"), "utf8")) as HardwarePrices; }
  catch { return { devices: [], cloud: [] }; }
}

export function loadSuggestions(): Record<string, ReturnType<typeof suggestDevice>> {
  try {
    const data = JSON.parse(fs.readFileSync(path.join(catalogRoot(), "hardware-suggestions.json"), "utf8")) as { suggestions?: Record<string, ReturnType<typeof suggestDevice>> };
    return data.suggestions ?? {};
  } catch { return {}; }
}

export function quoteSummary(device: Device) {
  const street = deviceStreetPrices(device);
  const quotes = deviceQuotes(device);
  return Object.entries(quotes).map(([currency, quote]) => ({
    currency,
    street: street[currency] ?? null,
    quote,
    sources: (device.prices ?? []).filter((price) => price.currency === currency)
  }));
}

export function suggestedDeviceFor(model: Model, prices = loadHardwarePrices()) {
  const suggestions = loadSuggestions();
  return suggestions[model.slug] ?? suggestDevice(model, prices.devices ?? []);
}

export function money(value: number | null | undefined, currency: string) {
  if (!Number.isFinite(value)) return "Not available";
  try { return new Intl.NumberFormat("en", { style: "currency", currency, maximumFractionDigits: 0 }).format(value as number); }
  catch { return `${currency} ${value}`; }
}

export function dateText(value: unknown) {
  if (typeof value !== "string" || value === "unknown" || !value) return "date not supplied";
  return value.slice(0, 10);
}
