import fs from "node:fs";
import path from "node:path";
import { catalogRoot } from "./catalog-root";

export type HwTier = { precision?: string | null; vram_gb?: number | null; gpu_examples?: string | null; ram_gb?: number | null; disk_gb?: number | null };
export type HwPrecision = { id: string; weights_gb?: number | null; min_vram_gb?: number | null; min_ram_gb?: number | null; disk_gb?: number | null };
export type HwCloud = { instance?: string | null; gpu?: string | null; usd_per_hour?: number | null; source?: string | null; eu_regions?: string | null; price_region?: string | null };
export type HardwareEntry = {
  slug: string;
  name: string;
  hf_repo?: string | null;
  params_total_b?: number | null;
  params_active_b?: number | null;
  architecture?: string;
  modalities?: string[];
  installer_supported?: boolean;
  source?: string;
  licence?: { spdx?: string | null; commercial_use?: string | null } | null;
  precisions?: HwPrecision[];
  min?: HwTier | null;
  recommended?: HwTier | null;
  cpu_only?: { possible?: boolean; note?: string } | null;
  apple_silicon?: { possible?: boolean; min_unified_memory_gb?: number | null; note?: string } | null;
  cloud?: { aws?: HwCloud | null; azure?: HwCloud | null; gcp?: HwCloud | null };
  notes?: string;
};

const SLUG = /^[a-z0-9](?:[a-z0-9.-]{0,118}[a-z0-9])?$/;

export function loadHardwareAll(file = path.join(catalogRoot(), "hardware-all.json")): HardwareEntry[] {
  let parsed: unknown;
  try {
    parsed = JSON.parse(fs.readFileSync(file, "utf8"));
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code === "ENOENT" || error instanceof SyntaxError) return [];
    throw error;
  }
  if (!parsed || typeof parsed !== "object") return [];
  return Object.entries(parsed as Record<string, unknown>)
    .filter(([slug, entry]) => !slug.startsWith("_") && SLUG.test(slug) && entry && typeof entry === "object" && typeof (entry as { name?: unknown }).name === "string")
    .map(([slug, entry]) => ({ ...(entry as Omit<HardwareEntry, "slug">), slug }))
    .sort((a, b) => a.name.localeCompare(b.name));
}

export function getHardware(slug: string): HardwareEntry | undefined {
  return loadHardwareAll().find((entry) => entry.slug === slug);
}

export function hasKnownHardware(entry?: HardwareEntry): boolean {
  return Boolean(entry?.min && Number(entry.min.vram_gb) > 0);
}

export const CLOUD_PROVIDERS = [
  { id: "aws", name: "AWS", image: "AWS Deep Learning AMI (GPU, Ubuntu)", quota: "Service Quotas → EC2 → “Running On-Demand G and VT instances” (or P instances)", private: "a security group that allows inbound SSH (port 22) only from your IP", where: "EC2 console" },
  { id: "azure", name: "Azure", image: "NVIDIA GPU-Optimized VM image (Marketplace) or the Ubuntu HPC image with NVIDIA drivers", quota: "Subscription → Usage + quotas → request vCPUs for the instance family in your region (NVadsA10v5 for A10, NCadsA100v4 for A100)", private: "a network security group that allows inbound SSH (port 22) only from your IP", where: "Virtual machines blade" },
  { id: "gcp", name: "Google Cloud", image: "Deep Learning VM (CUDA, Ubuntu)", quota: "IAM & Admin → Quotas → GPUs (all regions) and the specific GPU type in your region", private: "a firewall rule that allows inbound SSH (port 22) only from your IP", where: "Compute Engine console" }
] as const;

/** Cloud price sources are free text that may hold several URLs; the last one is the provider's own price page. */
export function sourceLink(source?: string | null): string | null {
  const urls = (source ?? "").match(/https?:\/\/[^\s;,)]+/g);
  return urls?.length ? urls[urls.length - 1] : null;
}
