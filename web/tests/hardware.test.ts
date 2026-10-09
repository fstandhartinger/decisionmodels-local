import { describe, expect, it } from "vitest";
import { deviceQuotes, deviceStreetPrices, marginQuote, median, suggestDevice } from "../lib/hardware-core.mjs";

describe("hardware prices", () => {
  it("uses a currency-specific median and the margin floor", () => {
    expect(median([100, 140, 120])).toBe(120);
    expect(deviceStreetPrices({ id: "x", name: "X", class: "gpu-workstation", memory_gb: 24, prices: [
      { value: 1000, currency: "USD", source: "a", date: "2026-10-09" },
      { value: 1200, currency: "USD", source: "b", date: "2026-10-09" },
      { value: 900, currency: "EUR", source: "c", date: "2026-10-09" }
    ] })).toEqual({ USD: 1100, EUR: 900 });
    expect(marginQuote(1000)).toBe(1309);
    expect(marginQuote(100)).toBe(259);
    expect(marginQuote(0)).toBeNull();
    expect(deviceQuotes({ id: "x", name: "X", class: "gpu-workstation", memory_gb: 24, prices: [{ value: 1000, currency: "USD", source: "a", date: "2026-10-09" }] })).toEqual({ USD: 1309 });
  });

  it("picks a device that fits the recommended memory and image needs", () => {
    const model = { params: { total_b: 3 }, modalities: ["text", "image"], installer_policy: { status: "supported" }, variants: [{ precision: "q4_k_m", min_vram_gb: 8, recommended_vram_gb: 12, platforms: ["linux-nvidia"] }] };
    const devices = [
      { id: "jetson", name: "Jetson", class: "jetson", memory_gb: 16, memory_kind: "unified", prices: [{ value: 500, currency: "USD", source: "a", date: "2026-10-09" }] },
      { id: "gpu", name: "GPU", class: "gpu-workstation", memory_gb: 16, memory_kind: "vram", supports_image: true, prices: [{ value: 900, currency: "USD", source: "b", date: "2026-10-09" }] },
      { id: "large", name: "Large GPU", class: "gpu-workstation", memory_gb: 24, memory_kind: "vram", supports_image: true, prices: [{ value: 1200, currency: "USD", source: "c", date: "2026-10-09" }] }
    ];
    expect(suggestDevice(model, devices)?.id).toBe("gpu");
    expect(suggestDevice({ ...model, installer_policy: { status: "excluded" } }, devices)).toBeNull();
    expect(suggestDevice({ ...model, variants: [{ precision: "bf16", min_vram_gb: 8, recommended_vram_gb: 12, platforms: ["linux-nvidia"] }] }, devices)?.id).toBe("gpu");
  });

  it("matches device class to the supported platform and uses host RAM when a unified-memory variant has no VRAM figure", () => {
    const model = { params: { total_b: 12 }, modalities: ["text"], installer_policy: { status: "supported" }, variants: [
      { id: "gpu-bf16", precision: "bf16", recommended_vram_gb: 96, min_ram_gb: 32, platforms: ["linux-nvidia"] },
      { id: "mps-fp16", precision: "fp16", recommended_vram_gb: 0, min_ram_gb: 48, platforms: ["macos-arm64"] }
    ] };
    const devices = [
      { id: "small-mac", name: "Small Mac", class: "apple-silicon", memory_gb: 16, memory_kind: "unified", prices: [{ value: 1000, currency: "USD", source: "a", date: "2026-10-09" }] },
      { id: "large-mac", name: "Large Mac", class: "apple-silicon", memory_gb: 64, memory_kind: "unified", prices: [{ value: 2000, currency: "USD", source: "b", date: "2026-10-09" }] },
      { id: "gpu", name: "GPU", class: "gpu-workstation", memory_gb: 96, memory_kind: "vram", prices: [{ value: 3000, currency: "USD", source: "c", date: "2026-10-09" }] }
    ];
    expect(suggestDevice(model, devices)).toMatchObject({ id: "large-mac", variant_id: "mps-fp16", memory_gb: 64 });
  });

  it("only suggests Jetson for a small quantised NVIDIA-compatible variant", () => {
    const model = { params: { total_b: 4 }, modalities: ["text"], installer_policy: { status: "supported" }, variants: [{ precision: "q4_k_m", recommended_vram_gb: 8, platforms: ["linux-nvidia"] }] };
    const device = { id: "jetson", name: "Jetson", class: "jetson", memory_gb: 8, memory_kind: "unified", prices: [{ value: 500, currency: "USD", source: "a", date: "2026-10-09" }] };
    expect(suggestDevice(model, [device])?.id).toBe("jetson");
    expect(suggestDevice({ ...model, params: { total_b: 5 } }, [device])).toBeNull();
    expect(suggestDevice({ ...model, variants: [{ precision: "bf16", recommended_vram_gb: 8, platforms: ["linux-nvidia"] }] }, [device])).toBeNull();
  });
});
